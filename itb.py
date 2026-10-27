#!/usr/bin/env python3
"""Inside the Block: measure intra-block ordering of own txs per leader.
Dry-run by default (build+simulate, never send). Live sending only with --live and a hard spend cap."""
import argparse, json, os, random, time, urllib.request, urllib.error, collections, datetime as dt
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.hash import Hash
from solders.instruction import Instruction
from solders.message import Message
from solders.transaction import Transaction
from solders.system_program import transfer, TransferParams
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price

RPC = os.environ.get("RPC_URL", "https://api.mainnet-beta.solana.com")
MEMO = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TzNpXJdK5E7JRB3ZW5Q3aM")
CLIENTS = ["AgaveBam", "JitoLabs", "HarmonicAgave", "HarmonicFiredancer", "Firedancer", "Agave", "Rakurai", "FireBAM"]
CU_LIMIT = 2000
BASE_FEE = 5000

def rpc(m, p=None):
    r = urllib.request.Request(RPC, json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p or []}).encode(),
                               {"content-type": "application/json"})
    for k in range(8):  # public RPC rate-limits (HTTP 429): exponential backoff
        try:
            out = json.load(urllib.request.urlopen(r, timeout=30)); break
        except urllib.error.HTTPError as e:
            if e.code != 429 or k == 7: raise
            time.sleep(0.5 * 2 ** k)
    if "error" in out: raise RuntimeError(f"{m}: {out['error']}")
    return out["result"]

def log(ev, **k):
    k.update(ev=ev, t=time.time(), utc=dt.datetime.utcnow().isoformat() + "Z")
    with open(ARGS.out + "/events.jsonl", "a") as f: f.write(json.dumps(k) + "\n")
    print(json.dumps(k))

def pick_validators(per_client=1):
    nodes = {n["pubkey"]: n for n in rpc("getClusterNodes")}
    votes = rpc("getVoteAccounts")["current"]
    slot = rpc("getSlot"); ep = rpc("getEpochInfo"); start = slot - ep["slotIndex"]
    sched = rpc("getLeaderSchedule", [None, {}]) or {}
    chosen = []
    for c in CLIENTS:
        cand = []
        for v in votes:
            n = nodes.get(v["nodePubkey"])
            if not n or n.get("clientId") != c: continue
            up = [start + i for i in sched.get(v["nodePubkey"], []) if start + i > slot + 200]
            if up: cand.append((v["activatedStake"], v["nodePubkey"], n.get("version"), up))
        cand.sort(reverse=True)
        for st, pk, ver, up in cand[:per_client]:
            chosen.append(dict(identity=pk, client=c, version=ver, stake_sol=st // 10**9, next_slots=up[:40]))
    return chosen

def build_tx(kp, bh, cu_price, tag):
    ixs = [set_compute_unit_limit(CU_LIMIT), set_compute_unit_price(cu_price),
           transfer(TransferParams(from_pubkey=kp.pubkey(), to_pubkey=kp.pubkey(), lamports=1)),
           Instruction(MEMO, tag.encode(), [])]
    return Transaction([kp], Message(ixs, kp.pubkey()), Hash.from_string(bh))

def fee_of(cu_price): return BASE_FEE + (cu_price * CU_LIMIT + 999_999) // 1_000_000

def main():
    os.makedirs(ARGS.out, exist_ok=True)
    kp = Keypair.from_bytes(bytes(json.load(open(ARGS.keypair))))
    cap = int(ARGS.cap_sol * 1e9); spent = 0
    bal = rpc("getBalance", [str(kp.pubkey())])["value"]
    log("start", mode="LIVE" if ARGS.live else "DRY", balance=bal, cap=cap, rpc=RPC)
    vals = pick_validators(ARGS.per_client)
    json.dump(vals, open(ARGS.out + "/validators.json", "w"), indent=1)
    for v in vals: log("validator", **{k: v[k] for k in ("identity", "client", "version", "stake_sol")})
    prices = ARGS.prices
    plan = []  # (slot, leader)
    for v in vals:
        # leader windows are 4 consecutive slots; target the 2nd slot of the next N windows
        ws = sorted({s - (s % 4) for s in v["next_slots"]})[:ARGS.windows]
        plan += [(w, v) for w in ws]
    plan.sort(key=lambda a: a[0])
    sent = []
    for w, v in plan:
        cost = fee_of(max(prices)) * len(prices) * 1
        if ARGS.live and spent + len(prices) * fee_of(max(prices)) > cap:
            log("cap_reached", spent=spent); break
        # wait until ~1 slot before window start
        while True:
            s = rpc("getSlot", [{"commitment": "processed"}])
            if s >= w - ARGS.lead_slots: break
            if s < w - 40: time.sleep(min(8, (w - 40 - s) * 0.4))
            else: time.sleep(0.25)
        if s > w + 2: log("missed_window", slot=w, now=s, leader=v["identity"]); continue
        bh = rpc("getLatestBlockhash", [{"commitment": "processed"}])["value"]["blockhash"]
        order = prices[:]; random.shuffle(order)  # randomise send order vs fee to decouple
        txs_ = []
        for i, p in enumerate(order):
            tag = f"itb|{v['client']}|w{w}|i{i}|p{p}|{random.randint(0,1<<30)}"
            tx = build_tx(kp, bh, p, tag)
            t0 = time.time()
            if ARGS.burst:  # build all first, then fire concurrently so they arrive ~together
                txs_.append((i, p, tag, tx)); continue
            if ARGS.live:
                try:
                    sig = rpc("sendTransaction", [__import__('base64').b64encode(bytes(tx)).decode(),
                              {"encoding": "base64", "skipPreflight": True, "maxRetries": 0}])
                    spent += fee_of(p)
                except Exception as e: log("send_err", err=str(e)); continue
            else:
                sim = rpc("simulateTransaction", [__import__('base64').b64encode(bytes(tx)).decode(),
                          {"encoding": "base64", "sigVerify": False, "replaceRecentBlockhash": True}])
                sig = str(tx.signatures[0]); log("simulated", err=sim["value"]["err"], cu=sim["value"].get("unitsConsumed"))
            rec = dict(sig=sig, target_window=w, leader=v["identity"], client=v["client"], version=v["version"],
                       send_idx=i, cu_price=p, send_t=t0, slot_at_send=s, tag=tag)
            sent.append(rec); log("sent" if ARGS.live else "dry_built", **rec)
            json.dump(sent, open(ARGS.out + "/sent.json", "w"), indent=1)  # incremental: survives crashes
            if ARGS.gap_ms: time.sleep(ARGS.gap_ms / 1000)
        if ARGS.burst and txs_:
            import base64, concurrent.futures as cf
            def fire(item):
                i, p, tag, tx = item; t0 = time.time()
                if not ARGS.live:
                    sim = rpc("simulateTransaction", [base64.b64encode(bytes(tx)).decode(),
                              {"encoding": "base64", "sigVerify": False, "replaceRecentBlockhash": True}])
                    return i, p, tag, str(tx.signatures[0]), t0, sim["value"]["err"]
                try:
                    return i, p, tag, rpc("sendTransaction", [base64.b64encode(bytes(tx)).decode(),
                              {"encoding": "base64", "skipPreflight": True, "maxRetries": 0}]), t0, None
                except Exception as e: return i, p, tag, None, t0, str(e)
            with cf.ThreadPoolExecutor(len(txs_)) as ex: res = list(ex.map(fire, txs_))
            for i, p, tag, sig, t0, err in res:
                if sig is None: log("send_err", err=err); continue
                if ARGS.live: spent += fee_of(p)
                rec = dict(sig=sig, target_window=w, leader=v["identity"], client=v["client"], version=v["version"],
                           send_idx=i, cu_price=p, send_t=t0, slot_at_send=s, tag=tag, burst=True)
                sent.append(rec); log("sent" if ARGS.live else "dry_built", **rec)
            json.dump(sent, open(ARGS.out + "/sent.json", "w"), indent=1)
    json.dump(sent, open(ARGS.out + "/sent.json", "w"), indent=1)
    log("done_sending", n=len(sent), est_spent=spent)
    if ARGS.live:
        time.sleep(30); collect(sent)

def collect(sent):
    sigs = [r["sig"] for r in sent]; st = {}
    for i in range(0, len(sigs), 200):
        for sg, x in zip(sigs[i:i+200], rpc("getSignatureStatuses", [sigs[i:i+200], {"searchTransactionHistory": True}])["value"]):
            st[sg] = x
    blocks = {}
    for r in sent:
        x = st.get(r["sig"]); r["landed"] = bool(x); 
        if not x: continue
        r["slot"] = x["slot"]
        if x["slot"] not in blocks:
            blocks[x["slot"]] = rpc("getBlock", [x["slot"], {"maxSupportedTransactionVersion": 1, "transactionDetails": "full",
                                    "encoding": "json", "rewards": True}])
            json.dump(blocks[x["slot"]], open(f"{ARGS.out}/block_{x['slot']}.json", "w"))
        b = blocks[x["slot"]]; txs = b["transactions"]
        for j, t in enumerate(txs):
            if t["transaction"]["signatures"][0] == r["sig"]:
                r.update(pos=j, n_block=len(txs), fee=t["meta"]["fee"], block_leader=next((w["pubkey"] for w in b.get("rewards", []) if w.get("rewardType") == "Fee"), None))
    json.dump(sent, open(ARGS.out + "/results.json", "w"), indent=1)
    import analyze; analyze.run(ARGS.out)

if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--live", action="store_true", help="really send (default: dry-run/simulate)")
    a.add_argument("--cap-sol", type=float, default=0.045)
    a.add_argument("--keypair", default=os.environ.get("KEYPAIR", "/keys/key.json"))
    a.add_argument("--out", default="data/run")
    a.add_argument("--per-client", type=int, default=1)
    a.add_argument("--windows", type=int, default=3)
    a.add_argument("--prices", type=int, nargs="+", default=[0, 1000, 10000, 100000, 500000])
    a.add_argument("--lead-slots", type=int, default=1)
    a.add_argument("--gap-ms", type=int, default=0)
    a.add_argument("--burst", action="store_true", help="send each probe group concurrently (tests fee priority)")
    a.add_argument("--collect", action="store_true")
    ARGS = a.parse_args()
    if ARGS.collect: collect(json.load(open(ARGS.out + "/sent.json")))
    else: main()
