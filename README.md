# Inside the Block — how Solana leaders order *our own* transactions

One command: `KEY_DIR=/path/to/keydir docker compose run --rm itb` (dry-run). Live: `ITB_ARGS="--live --burst --cap-sol 0.045 --windows 3 --out data/live2" docker compose run --rm itb`.
Keys are mounted read-only from `KEY_DIR` (never in repo, `.gitignore`d).

## Design
* **Validator selection** (`pick_validators`): `getClusterNodes.clientId` + `version` joined with `getVoteAccounts`; highest-stake node per client family with leader slots ≥200 slots ahead: AgaveBam, JitoLabs (Jito-Agave), HarmonicAgave, HarmonicFiredancer, Firedancer, FireBAM, Rakurai, Agave (vanilla) — 8 validators, ≥3 clients (4.3.2 Agave forks vs 26.10.4 Firedancer forks). Snapshot saved to `validators.json` per run.
* **Leader windows**: `getLeaderSchedule` (epoch-relative → absolute). Windows are 4 slots; we fire 1 slot before the window start (`--lead-slots`).
* **Probe group**: per window, K=5 self-transfers (1 lamport to self) + Memo tag `itb|client|window|send_idx|price|nonce`, CU limit 2000, CU prices {0,1e3,1e4,1e5,5e5} µlamports, **sent in random order** so send order and fee are decorrelated. All share the same fee payer → they write-lock the same account, so they cannot be scheduled in parallel; their relative position inside the block is entirely the scheduler's choice.
* **Metrics**: per (client, slot) group, Kendall τ between fee rank and block position (+1 = strict priority order) and between send index and position (+1 = FIFO). τ≈0 across groups ⇒ "no rule / noise".
* **Spend cap**: worst-case fee per tx = 5000 + ceil(price·2000/1e6) lamports (≤6000); a window is skipped once spent+worst-case would exceed `--cap-sol` (default 0.045). Dry-run (default) only builds + `simulateTransaction`.
* **Verification**: `sent.json`/`results.json` contain every signature, target window, landed slot, block index, fee; raw `getBlock` JSON saved as `block_<slot>.json`.

## What we account for
* *Path to leader*: we use a public RPC `sendTransaction` (maxRetries 0, skipPreflight). The RPC forwards over QUIC to current/next leaders; stake-weighted QoS and forwarding add jitter. Arrival order at the leader ≠ our send order — this is why fee is randomised vs send order and why we report both τ's.
* *Own-tx interaction*: shared writable fee-payer forces serialisation (by design).
* *Competition*: block size and position are recorded; position is analysed only relative to our own txs.
* *Jito bundles/tips*: out of scope; we send no tips, and our txs never enter bundles.
* *Alpenglow*: all measurements after Oct 21 2026 (not mixed).
## What it does NOT separate
Leader-side arrival time (we can't observe it), RPC-forwarding reordering vs scheduler reordering, landing in a later slot of the window or next leader (recorded and flagged via `block_leader`).

## Modes
* default: dry-run (build + simulateTransaction, nothing sent).
* `--live`: send, capped by `--cap-sol`.
* `--burst`: fire each 5-tx probe group concurrently (tests fee priority); without it txs are sent serially (tests FIFO).
* `--collect --out DIR`: re-fetch statuses/blocks for an existing `sent.json`.

Results: see REPORT.md.
* Raw blocks stored as `block_<slot>.json.gz`.

## Support this research

If this was useful, tips are welcome (SOL / USDC / USDT on Solana):

`mwcCTqQvsuTipRmW712oLofMyusP8YdgVunkGZheBKu`

Tips fund more mainnet runs (more validators, more clients, continuous monitoring).
