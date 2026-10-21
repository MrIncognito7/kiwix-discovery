# Evaluation

25 queries with relevance judgments (`eval/queries_labels.json`), k=10.

| Query | #rel | nDCG baseline | nDCG intent | nDCG semantic | nDCG hybrid |
|---|---|---|---|---|---|
| teach science to 12-year-olds | 9 | 0.34 | 0.35 | 0.00 | 0.35 |
| learn French | 6 | 0.26 | 0.39 | 0.37 | 0.57 |
| prepare for natural disasters | 13 | 0.34 | 0.65 | 0.62 | 0.77 |
| medical resources under 2 GB | 3 | 0.16 | 0.79 | 0.23 | 0.34 |
| programming for beginners | 26 | 0.14 | 0.22 | 0.31 | 0.42 |
| Spanish dictionary | 2 | 0.69 | 0.61 | 0.61 | 0.79 |
| first aid and emergency medicine | 4 | 0.39 | 0.64 | 0.39 | 0.51 |
| high school math | 6 | 0.00 | 0.11 | 0.00 | 0.00 |
| chemistry for students | 7 | 0.79 | 0.70 | 0.09 | 0.70 |
| farming and gardening | 5 | 0.72 | 0.97 | 1.00 | 1.00 |
| water purification and sanitation | 5 | 0.55 | 0.55 | 0.45 | 0.55 |
| repair electronics at home | 6 | 0.44 | 0.61 | 0.40 | 0.68 |
| linux help | 7 | 0.32 | 0.48 | 0.40 | 0.41 |
| TED talks about technology | 10 | 0.22 | 0.22 | 0.57 | 0.60 |
| world history | 5 | 0.47 | 0.53 | 0.00 | 0.53 |
| classic books to read | 42 | 0.08 | 0.91 | 0.06 | 0.79 |
| travel guide and maps | 3 | 0.67 | 0.77 | 0.70 | 0.95 |
| cooking recipes | 6 | 0.99 | 0.99 | 0.96 | 0.97 |
| learn English grammar | 6 | 0.62 | 0.34 | 0.15 | 0.63 |
| learn Hindi | 3 | 0.44 | 0.47 | 0.30 | 0.63 |
| Arabic school resources for children | 15 | 0.00 | 0.00 | 0.79 | 0.57 |
| physics simulations | 5 | 0.65 | 0.84 | 0.00 | 0.79 |
| offline encyclopedia under 10 GB | 5 | 0.10 | 0.11 | 0.00 | 0.10 |
| learn to code in JavaScript | 19 | 0.14 | 0.56 | 1.00 | 0.56 |
| biology for high school | 5 | 0.58 | 0.60 | 0.13 | 0.73 |

| Method | P@10 | Recall@10 | nDCG@10 | MRR |
|---|---|---|---|---|
| baseline | 0.232 | 0.427 | 0.405 | 0.568 |
| intent | 0.296 | 0.472 | 0.537 | 0.805 |
| semantic | 0.244 | 0.336 | 0.381 | 0.557 |
| hybrid | 0.376 | 0.566 | 0.598 | 0.772 |

nDCG, hybrid vs baseline: better on 20, tied on 2, worse on 3 queries.
