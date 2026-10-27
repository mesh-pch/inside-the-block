# Inside the Block — Report (DRAFT)
Measurement dates: dry-run 2026-10-27 12:51–12:56 UTC (epoch 1069, post-Alpenglow). Live runs (mainnet, epoch 1069, post-Alpenglow): live1 13:00–13:02 UTC (serial, crashed on RPC 429 after 5 windows, collected afterwards), live2 13:08–13:20 UTC (`--burst`, 8 clients × 3 windows), live3 13:20–13:40 UTC (serial, 8 × 3). 265 txs sent, **265/265 landed**, total fees 1,389,766 lamports (0.00139 SOL).

## Method
See repo README. 8 validators, 1 per client family (table below), 5 probe txs/window with random send order vs CU price; Kendall τ of fee→position and send→position.

## Validators
| client | identity | version | stake (SOL) |
|---|---|---|---|
| AgaveBam | DRpbCBMxVnDK7maPM5tGv6MvB3v1sRMC86PZ8okm21hy | 4.3.2 | 12.66M |
| JitoLabs | HEL1USMZKAL2odpNBj2oCjffnFGaYwmbGmyewGv1e2TU | 4.3.2 | 16.64M |
| HarmonicAgave | Fd7btgySsrjuo25CJCj7oE7VPMyezDhnx7pZkj2v69Nk | 4.3.2 | 17.06M |
| HarmonicFiredancer | JUPiTERrZqgf1jUyR7dSkhMx4Kn2qJyekWsg3LT1h4b | 26.10.4 | 9.72M |
| Firedancer | 9eGrDohdNTAo61DRHyfMuqKWXqYnA3i254Wiszxe8FoY | 26.10.4 | 7.04M |
| FireBAM | 9jxgosAfHgHzwnxsHw4RAZYaLVokMbnYtmiZBreynGFP | 26.10.4 | 4.48M |
| Rakurai | ana2y2YvQ3ZPMwm6qhnN3nJoUSiT3qx5Pvetkq9xcfY | 4.3.2 | 2.27M |
| Agave | 7QQGNm3ptwinipDCyaCF7jY5katgmFUu1ieP2f7nwLpE | 4.3.2 | 1.88M |

## Dry-run result
All 8 targeted windows reached on time (slot_at_send = window−1), 40 txs built+simulated, 0 sent, 0 lamports spent.

## Results (pairwise: share of own-tx pairs in the same block where the higher CU-price tx sits earlier; 50% = random)
| client | version | live2 burst (arrive together) | live3 serial | live1 serial |
|---|---|---|---|---|
| Firedancer | 26.10.4 | **25/30 (83%)** | 4/10 | 2/6 |
| HarmonicFiredancer | 26.10.4 | **21/26 (81%)** | 2/6 | – |
| FireBAM | 26.10.4 | **19/26 (73%)** | 6/10 | – |
| AgaveBam | 4.3.2 | 20/30 (67%) | 4/12 | 1/4 |
| HarmonicAgave | 4.3.2 | 20/30 (67%) | 6/8 | 2/3 |
| JitoLabs | 4.3.2 | 17/30 (57%) | 2/9 | 2/3 |
| Rakurai | 4.3.2 | 12/24 (50%) | 4/8 | – |
| Agave (vanilla) | 4.3.2 | 11/26 (42%) | 2/8 | – |

Send order → position, serial runs: Kendall τ(send) = **+1.00 for every client** in live1 and live3 (every multi-tx group): when txs arrive ~100 ms apart, all 8 schedulers are effectively FIFO and fee is irrelevant. In burst mode τ(send) averages ~0 (−0.20…+0.43), as expected when arrival order is random.
Burst groups landed in a single slot 20/24 times and always in the target leader's block; their positions are often contiguous (e.g. HarmonicFiredancer slot 462082314: p500000@130, p100000@131, p1000@132, p0@133, p10000@134), i.e. the batch was scheduled together.
Full per-block tables: `data/live1|2|3/analysis.md`; raw blocks `block_<slot>.json`; every signature in `results.json`.

## Conclusions
1. Arrival time dominates. Any tx that arrives one RPC round-trip (~100 ms) earlier lands earlier regardless of a 500× higher priority fee, on all clients.
2. Among near-simultaneous arrivals, the Firedancer family (Firedancer, HarmonicFiredancer, FireBAM) orders most consistently by fee (73–83% of pairs); Agave forks with BAM/Harmonic are weaker (~67%); JitoLabs is near-random (57%); Rakurai and vanilla Agave show no fee ordering in our sample (≤50%).
3. Sample is small (≈25–30 pairs/client in burst mode, 3 blocks each); differences between neighbouring clients (e.g. 67% vs 57%) are not significant. The Firedancer-vs-vanilla-Agave gap is the most robust signal.

## What went wrong
* First dry-runs missed windows: selection (getLeaderSchedule ~20 s) consumed the 30-slot margin → raised to 200 slots.
* getLatestBlockhash parsing bug (fixed).
* live1 crashed on HTTP 429 from the public RPC → added exponential backoff, incremental `sent.json`, slower slot polling; live1 data recovered from `events.jsonl` and collected with `--collect`.
* `getBlock` failed with "Transaction version (1) is not supported" → `maxSupportedTransactionVersion: 1`.
* analyze.py Kendall bug (pairs unpacked wrongly → τ always ±1); fixed, all tables regenerated.
* Serial sending spreads 5 txs over ~2–4 slots; in live3 78/120 txs landed in the *next* leader's block (`block_leader` ≠ target), so serial per-client attribution is weak → `--burst` mode (concurrent sends) added; use live2 for per-client conclusions.
* Not separated: RPC/QUIC forwarding reordering vs scheduler reordering; leader-side arrival time is unobservable.
