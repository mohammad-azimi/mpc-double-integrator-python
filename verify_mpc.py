"""Independent numerical checks for the MPC implementation. Run after simulation."""

import itertools
import json
from pathlib import Path

import numpy as np

from mpc_simulation import LinearMPC, SCENARIOS, plant_matrices


def exact_small_qp_solution(H, f, limit):
    """Enumerate free/lower/upper active sets, independently of SciPy SLSQP."""
    candidates = []
    for status in itertools.product((-1, 0, 1), repeat=len(f)):
        status = np.array(status)
        active, free = np.flatnonzero(status), np.flatnonzero(status == 0)
        u = status.astype(float) * limit
        if len(free):
            u[free] = np.linalg.solve(H[np.ix_(free, free)],
                         -f[free] - H[np.ix_(free, active)] @ u[active])
        if np.max(np.abs(u)) <= limit + 1e-10:
            candidates.append((0.5 * u @ H @ u + f @ u, u.copy()))
    return min(candidates, key=lambda item: item[0])[1]


def main():
    # Exact constant acceleration from zero for one second.
    A, B, _ = plant_matrices(0.1)
    x = np.zeros(2)
    for _ in range(10):
        x = A @ x + B
    np.testing.assert_allclose(x, [0.5, 1.0], atol=1e-12)

    checked = 0
    for settings in SCENARIOS:
        controller = LinearMPC(settings)
        assert np.min(np.linalg.eigvalsh(controller.H)) > 0
        # Compare prediction matrices against direct plant roll-out.
        state = np.array([0.2, -0.3])
        plan = np.array([0.1, -0.2, 0.3])
        direct, x = [], state.copy()
        for k in range(settings.prediction_horizon):
            x = controller.A @ x + controller.B * plan[min(k, len(plan) - 1)]
            direct.append(x[0])
        np.testing.assert_allclose(controller.F @ state + controller.G @ plan, direct, atol=1e-12)
        # Check gradient and compare SLSQP with an independent exact active-set method.
        for state, previous in [(np.zeros(2), 0.0), (np.array([1.2, 0.4]), 0.2),
                                 (np.array([0.9, -0.1]), -0.1)]:
            f = controller.linear_term(state, previous)
            def objective(u):
                return 0.5 * u @ controller.H @ u + f @ u
            numeric = np.array([
                (objective(plan + 1e-5 * direction) - objective(plan - 1e-5 * direction)) / 2e-5
                for direction in np.eye(len(plan))])
            np.testing.assert_allclose(controller.H @ plan + f, numeric, atol=1e-8)
            expected = exact_small_qp_solution(controller.H, f, settings.input_limit)
            actual, _, _ = controller.control(state, previous)
            np.testing.assert_allclose(actual, expected[0], atol=3e-5)
            checked += 1

    directory = Path(__file__).resolve().parent / "results"
    for settings in SCENARIOS:
        data = np.genfromtxt(directory / f"{settings.slug}.csv", names=True, delimiter=",")
        u = data["input"][:-1]
        assert np.max(np.abs(u)) <= settings.input_limit + 1e-9
        assert np.max(data["optimality_residual"][:-1]) < 2e-5
        assert abs(data["position"][-1] - settings.reference) < 1e-4
        A, B, _ = plant_matrices(settings.sample_time)
        states = np.column_stack([data["position"], data["velocity"]])
        np.testing.assert_allclose(states[1:], states[:-1] @ A.T + u[:, None] * B, atol=1e-12)

    result = {"status": "PASS", "independent_qp_cases": checked,
              "checks": ["exact physical discretization", "prediction matrix roll-out",
                         "analytic gradient", "positive definite cost Hessian",
                         "independent active-set QP comparison", "saved trajectory dynamics",
                         "input bounds", "optimality residuals", "final tracking errors"]}
    (directory / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
