# Model Predictive Control of a Double Integrator in Python

An independent Python adaptation of the MathWorks example **Model Predictive
Control of a Single-Input-Single-Output Plant** for Practical task 04.

## Run

Use Python 3.10 or newer. Open a terminal in this folder, then run:

```bash
python -m pip install -r requirements.txt
python mpc_simulation.py
python verify_mpc.py
python make_report.py
```

On Windows, `py` can replace `python` if needed. The code uses a noninteractive
Matplotlib backend, so it saves figures rather than opening plot windows.

## Model and method

The continuous plant is y'' = u with zero initial position and velocity. The
discrete plant uses the exact zero-order-hold equations. At each 0.1 s sample,
MPC optimizes a sequence of 3 inputs, penalizing predicted output errors and
input changes. The final planned input is held after the control horizon.
Only the first input is applied, and the problem is solved again at the next
sample. SciPy SLSQP solves the strictly convex quadratic problem with box bounds.

Three simulations each last 10 s, tracking the constant reference r = 1:

| Scenario | Prediction horizon | Control horizon | Input bounds |
| --- | ---: | ---: | --- |
| Baseline | 10 | 3 | -1 to 1 |
| Tighter input limit | 10 | 3 | -0.4 to 0.4 |
| Longer prediction horizon | 20 | 3 | -1 to 1 |

Change the `SCENARIOS` tuple in `mpc_simulation.py` to explore other settings.
If you change scenarios, rerun the simulation and update report discussion as
needed; the supplied report text interprets the three delivered scenarios.

## Files

- `mpc_simulation.py`: MPC, plant simulation, plots and numeric exports.
- `verify_mpc.py`: numerical verification, including independent QP solutions.
- `make_report.py`: regenerates the English Word report from saved results.
- `README_FA.md`: Persian explanation and execution guide.
- `results/*.csv`: trajectories and summary metrics; the final trajectory row
  contains a terminal state, so its input and solver fields are intentionally blank.
- `results/*.png`: model diagram, mathematical equations and comparison plots.
- `results/metrics.json`: numerical metrics and all scenario settings.
- `results/verification.json`: completed numerical check record.
- `MPC_Python_Report.docx`: the English class report.
- `MPC_Python_Report.pdf`: the matching PDF version of the report.
- `assets/cover_artwork.png`: university artwork reused from the supplied
  report template; the generator needs this file to reproduce the cover.
- `assets/baseline_response.png`: plot of the delivered baseline CSV data.

The report follows the supplied sample: an A4 university cover followed by
an introduction, implementation steps, code excerpts, figures and results.
Body page numbering starts at 1 after the cover. The document generator
recreates the Word file; PDF conversion requires a Word-compatible PDF exporter.

RMSE uses every sampled output including the initial and terminal values. IAE
uses the trapezoidal approximation over 0 to 10 s. Settling time is the first
sample after the last excursion outside a 2% reference band, provided no later
sample leaves the band within the simulated interval. This finite simulation
does not prove asymptotic stability.

## Scope

The assignment explicitly requests MATLAB/Simulink. This project implements
the selected example's plant and MPC concept in Python; acceptance of that
software substitution is a class requirement to resolve with the instructor.
No Simulink model or MATLAB execution is included.

The controller receives exact simulated position and velocity. There is no
measurement noise, Kalman filter, output-disturbance estimator, model mismatch,
terminal constraint or terminal cost. Its plots are original Python simulation
results, not claimed numerical replicas of the MathWorks implementation.
No training dataset or neural network is needed for this model-based MPC.

## References

1. MathWorks. Model Predictive Control of a Single-Input-Single-Output Plant.
   https://www.mathworks.com/help/mpc/gs/control-of-a-single-input-single-output-plant.html
2. SciPy. scipy.optimize.minimize with method SLSQP.
   https://docs.scipy.org/doc/scipy/reference/optimize.minimize-slsqp.html

Tested with Python 3.12, NumPy 2.3.5, SciPy 1.17.0, Matplotlib 3.10.8 and
python-docx 1.2.0. The requirements allow compatible versions.
