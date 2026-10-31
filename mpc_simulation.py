"""Constrained linear MPC for a double integrator, implemented in Python.

Run: python mpc_simulation.py
Outputs: results/*.png, three time-series CSVs, metrics.csv and metrics.json.

The plant and baseline tuning follow the MathWorks SISO MPC example.
This is an independent implementation with exact state feedback, not a
MATLAB/Simulink execution or a numerical reproduction of its estimator.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import numpy as np
from scipy.optimize import minimize


@dataclass(frozen=True)
class Settings:
    label: str
    slug: str
    prediction_horizon: int = 10
    control_horizon: int = 3
    sample_time: float = 0.1
    input_limit: float = 1.0
    tracking_weight: float = 1.0
    move_weight: float = 0.1
    duration: float = 10.0
    reference: float = 1.0

    def __post_init__(self):
        if not 1 <= self.control_horizon <= self.prediction_horizon:
            raise ValueError("Require 1 <= control horizon <= prediction horizon.")
        if min(self.sample_time, self.input_limit, self.duration,
               self.tracking_weight, self.move_weight) <= 0:
            raise ValueError("Times, input limit and weights must be positive.")
        if not np.isclose(self.duration / self.sample_time,
                          round(self.duration / self.sample_time)):
            raise ValueError("Duration must contain an integer number of samples.")


SCENARIOS = (
    Settings("Baseline", "baseline"),
    Settings("Tighter input limit", "tighter_input", input_limit=0.4),
    Settings("Longer prediction horizon", "longer_horizon", prediction_horizon=20),
)


def plant_matrices(sample_time):
    """Exact zero-order-hold discretization of y'' = u for constant input."""
    ts = sample_time
    return (np.array([[1.0, ts], [0.0, 1.0]]),
            np.array([0.5 * ts**2, ts]), np.array([1.0, 0.0]))


class LinearMPC:
    def __init__(self, settings):
        self.settings = settings
        self.A, self.B, self.C = plant_matrices(settings.sample_time)
        p, m = settings.prediction_horizon, settings.control_horizon
        # Predicted outputs: Y = F @ x + G @ U.
        # U has m elements; its final element is held for the remaining horizon.
        self.F = np.vstack([self.C @ np.linalg.matrix_power(self.A, i + 1)
                            for i in range(p)])
        self.G = np.zeros((p, m))
        for i in range(p):
            for j in range(i + 1):
                self.G[i, min(j, m - 1)] += (
                    self.C @ np.linalg.matrix_power(self.A, i - j) @ self.B)
        self.D = np.eye(m)
        self.D[np.arange(1, m), np.arange(m - 1)] = -1.0
        # J = 0.5 U.T H U + f.T U + a constant independent of U.
        self.H = 2 * (settings.tracking_weight * self.G.T @ self.G
                      + settings.move_weight * self.D.T @ self.D)
        self.guess = np.zeros(m)

    def linear_term(self, state, previous_input):
        s = self.settings
        previous = np.zeros(s.control_horizon)
        previous[0] = previous_input
        return 2 * (s.tracking_weight * self.G.T @ (self.F @ state - s.reference)
                    - s.move_weight * self.D.T @ previous)

    def control(self, state, previous_input):
        """Solve the convex bounded QP and apply only its first control move."""
        s = self.settings
        f = self.linear_term(state, previous_input)
        result = minimize(
            lambda u: 0.5 * u @ self.H @ u + f @ u,
            self.guess,
            jac=lambda u: self.H @ u + f,
            method="SLSQP",
            bounds=[(-s.input_limit, s.input_limit)] * s.control_horizon,
            options={"ftol": 1e-12, "maxiter": 150},
        )
        if not result.success or not np.all(np.isfinite(result.x)):
            raise RuntimeError(f"MPC optimization failed: {result.message}")
        gradient = self.H @ result.x + f
        residual = float(np.max(np.abs(
            result.x - np.clip(result.x - gradient, -s.input_limit, s.input_limit))))
        if np.max(np.abs(result.x)) > s.input_limit + 1e-9 or residual > 2e-5:
            raise RuntimeError("MPC feasibility or optimality verification failed.")
        # A shifted solution is the initial guess at the next sample.
        self.guess = np.r_[result.x[1:], result.x[-1]]
        return float(result.x[0]), residual, int(result.nit)


def simulate(settings):
    controller = LinearMPC(settings)
    n = round(settings.duration / settings.sample_time)
    time = np.arange(n + 1) * settings.sample_time
    state = np.zeros((n + 1, 2))
    inputs, residuals, iterations = np.zeros(n), np.zeros(n), np.zeros(n, dtype=int)
    previous_input = 0.0
    for k in range(n):
        inputs[k], residuals[k], iterations[k] = controller.control(state[k], previous_input)
        state[k + 1] = controller.A @ state[k] + controller.B * inputs[k]
        previous_input = inputs[k]
    return {"settings": settings, "time": time, "state": state, "input": inputs,
            "optimality_residual": residuals, "solver_iterations": iterations}


def metrics(run):
    s, t, y, u = run["settings"], run["time"], run["state"][:, 0], run["input"]
    error = s.reference - y
    outside = np.flatnonzero(np.abs(error) > 0.02 * abs(s.reference))
    settling = (0.0 if len(outside) == 0 else
                float(t[outside[-1] + 1]) if outside[-1] < len(t) - 1 else None)
    return {
        "scenario": s.label,
        "prediction_horizon": s.prediction_horizon,
        "control_horizon": s.control_horizon,
        "input_limit": s.input_limit,
        "rmse": float(np.sqrt(np.mean(error**2))),
        "iae": float(np.sum(0.5 * (np.abs(error[:-1]) + np.abs(error[1:]))) * s.sample_time),
        "settling_time_2pct_s": settling,
        "overshoot_pct": float(100 * max(0.0, np.max(y) - s.reference) / abs(s.reference)),
        "peak_abs_input": float(np.max(np.abs(u))),
        "final_abs_error": float(abs(error[-1])),
        "input_squared_integral": float(s.sample_time * np.sum(u**2)),
        "max_optimality_residual": float(np.max(run["optimality_residual"])),
        "optimization_solves": len(u),
    }


def save_csv(path, rows):
    rows = list(rows)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save_timeseries(run, directory):
    n = len(run["input"])
    save_csv(directory / f"{run['settings'].slug}.csv", (
        {"time_s": float(t), "position": float(run["state"][k, 0]),
         "velocity": float(run["state"][k, 1]), "reference": run["settings"].reference,
         "input": float(run["input"][k]) if k < n else "",
         "optimality_residual": float(run["optimality_residual"][k]) if k < n else "",
         "solver_iterations": int(run["solver_iterations"][k]) if k < n else ""}
        for k, t in enumerate(run["time"])))


def plot_responses(runs, directory):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False})
    colors = ["#1665A8", "#D47524", "#278168"]
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True, layout="constrained")
    for run, color in zip(runs, colors):
        axes[0].plot(run["time"], run["state"][:, 0], label=run["settings"].label,
                     color=color, lw=2)
        axes[1].stairs(run["input"], run["time"], color=color, lw=1.8)
    axes[0].axhline(1.0, color="#303030", ls="--", lw=1, label="Reference")
    axes[0].axhspan(0.98, 1.02, color="#D9E5DB", alpha=0.6, label="2% band")
    axes[0].set(ylabel="Output position y", title="Output tracking")
    axes[0].legend(loc="lower right", fontsize=9, ncols=2)
    for limit, color in [(1.0, colors[0]), (0.4, colors[1])]:
        for sign in [-1, 1]:
            axes[1].axhline(sign * limit, color=color, lw=0.8, ls=":", alpha=0.7)
    axes[1].set(xlabel="Time (s)", ylabel="Control input u", title="Bounded control input",
                xlim=(0, runs[0]["settings"].duration))
    for axis in axes:
        axis.grid(True, color="#DDDDDD", alpha=0.7)
    fig.savefig(directory / "response_comparison.png", dpi=240)
    plt.close(fig)


def plot_structure(directory):
    fig, ax = plt.subplots(figsize=(9, 2.5))
    ax.set(xlim=(0, 10), ylim=(0, 3))
    ax.axis("off")
    for x, width, label in [(0.15, 1.6, "Reference\nr = 1"),
                            (2.7, 2.0, "MPC controller\nbounded QP"),
                            (5.8, 2.0, "Double integrator\n" + r"$G(s)=1/s^2$")]:
        ax.add_patch(FancyBboxPatch((x, 1.45), width, 0.95,
                     boxstyle="round,pad=0.04", facecolor="#EDF3F8", edgecolor="#335C7A"))
        ax.text(x + width / 2, 1.925, label, ha="center", va="center", fontsize=11)
    for start, end in [((1.8, 1.92), (2.65, 1.92)),
                       ((4.75, 1.92), (5.75, 1.92)),
                       ((7.85, 1.92), (9.4, 1.92))]:
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=14, color="#24465E"))
    ax.text(5.25, 2.15, "u", ha="center")
    ax.text(9.55, 1.92, "y", va="center", fontsize=12)
    ax.plot([6.8, 6.8, 3.7], [1.4, 0.55, 0.55], color="#24465E", lw=1.2)
    ax.add_patch(FancyArrowPatch((3.7, 0.55), (3.7, 1.4), arrowstyle="-|>",
                 mutation_scale=14, color="#24465E"))
    ax.text(5.5, 0.12, "Exact simulated state feedback x = [y, v]", ha="center", fontsize=10)
    fig.savefig(directory / "control_structure.png", dpi=240, bbox_inches="tight")
    plt.close(fig)


def plot_equations(directory):
    formulas = {
        "plant_equations.png": [
            r"$\ddot{y}(t)=u(t),\qquad G(s)=\frac{1}{s^2}$",
            r"$y_{k+1}=y_k+T_s v_k+\frac{T_s^2}{2}u_k,\qquad v_{k+1}=v_k+T_s u_k$"],
        "cost_equations.png": [
            r"$\min_U J=\sum_{i=1}^{N_p}q(\hat{y}_{k+i\mid k}-r)^2"
            r"+\sum_{j=0}^{N_c-1}\rho(\Delta u_{k+j})^2$",
            r"$-u_{\max}\leq u_{k+j}\leq u_{\max},\qquad"
            r"\Delta u_{k+j}=u_{k+j}-u_{k+j-1}$"],
    }
    for filename, lines in formulas.items():
        fig = plt.figure(figsize=(9, 1.2))
        for index, formula in enumerate(lines):
            fig.text(0.5, 0.72 - index * 0.48, formula, ha="center", va="center", fontsize=16)
        fig.savefig(directory / filename, dpi=300, bbox_inches="tight", transparent=True)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "results")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    runs = [simulate(settings) for settings in SCENARIOS]
    rows = [metrics(run) for run in runs]
    for run in runs:
        save_timeseries(run, args.output_dir)
    save_csv(args.output_dir / "metrics.csv", rows)
    payload = {"settings": [asdict(s) for s in SCENARIOS], "metrics": rows}
    (args.output_dir / "metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    plot_responses(runs, args.output_dir)
    plot_structure(args.output_dir)
    plot_equations(args.output_dir)
    for row in rows:
        print(f"{row['scenario']}: settling {row['settling_time_2pct_s']:.1f} s, "
              f"overshoot {row['overshoot_pct']:.2f}%, RMSE {row['rmse']:.4f}")
    print(f"Results saved to {args.output_dir}")


if __name__ == "__main__":
    main()
