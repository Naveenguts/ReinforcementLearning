This evaluation compared the dummy and Hugging Face baselines across the steady_state, port_strike, and black_swan presets. Across 6 runs, the average grader score was 0.6586, the average final reward was 148.67, and the average cumulative reward was 278.26. The runs delivered 18 orders in total, incurred 0 late orders, kept inventory positive in 83% of runs, and reached termination in 83% of runs.

Key points:
- dummy: average score 0.5984, average final reward 160.99, average delivered 3.00, completed 3/3 runs.
- huggingface: average score 0.7187, average final reward 136.35, average delivered 3.00, completed 2/3 runs.
- black_swan: best score 0.3732 and final reward 85.57 from dummy, delivered 2, late 0.
- port_strike: best score 1.0000 and final reward 226.46 from huggingface, delivered 4, late 0.
- steady_state: best score 0.7452 and final reward 182.59 from huggingface, delivered 3, late 0.

Run matrix:

| backend | task | score | delivered | late | final reward | total reward | steps | done |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dummy | steady_state | 0.5203 | 3 | 0 | 172.94 | 110.17 | 4 | True |
| dummy | port_strike | 0.9018 | 4 | 0 | 224.46 | 365.01 | 6 | True |
| dummy | black_swan | 0.3732 | 2 | 0 | 85.57 | 98.15 | 5 | True |
| huggingface | steady_state | 0.7452 | 3 | 0 | 182.59 | 222.61 | 4 | True |
| huggingface | port_strike | 1.0000 | 4 | 0 | 226.46 | 737.72 | 8 | True |
| huggingface | black_swan | 0.4109 | 2 | 0 | 0.00 | 135.89 | 20 | False |
