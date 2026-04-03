This evaluation compared the dummy and Hugging Face baselines across the steady_state, port_strike, and black_swan presets. Across 6 runs, the average final reward was 183.42 and the average cumulative reward was 304.11. The runs delivered 19 orders in total, incurred 0 late orders, kept inventory positive in 100% of runs, and reached termination in 83% of runs.

Key points:
- dummy: average final reward 134.37, average delivered 2.33, completed 2/3 runs.
- huggingface: average final reward 232.47, average delivered 4.00, completed 3/3 runs.
- black_swan: best final reward 278.02 from huggingface, delivered 5, late 0.
- port_strike: best final reward 236.81 from huggingface, delivered 4, late 0.
- steady_state: best final reward 182.59 from huggingface, delivered 3, late 0.
