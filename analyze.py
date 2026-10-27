import json, collections, itertools
def kendall(xs, ys):
    c = d = 0
    for (a, x), (b, y) in itertools.combinations(zip(xs, ys), 2):  # pairs of (rank, pos)
        s = (a - b) * (x - y)
        c += s > 0; d += s < 0
    return (c - d) / max(1, c + d)
def run(out):
    R = [r for r in json.load(open(out + "/results.json")) if r.get("pos") is not None]
    by = collections.defaultdict(list)
    for r in R: by[(r["client"], r["slot"])].append(r)
    rows, agg = [], collections.defaultdict(lambda: dict(fee=[], send=[], n=0, groups=0))
    for (c, s), g in sorted(by.items()):
        if len(g) < 2: continue
        tf = kendall([-x["cu_price"] for x in g], [x["pos"] for x in g])   # +1 = higher fee earlier
        ts = kendall([x["send_idx"] for x in g], [x["pos"] for x in g])    # +1 = FIFO
        a = agg[c]; a["fee"].append(tf); a["send"].append(ts); a["n"] += len(g); a["groups"] += 1
        rows.append(f"| {c} | {s} | {len(g)} | {g[0]['n_block']} | {tf:+.2f} | {ts:+.2f} | " +
                    ", ".join(f"p{x['cu_price']}@{x['pos']}" for x in sorted(g, key=lambda x: x['pos'])) + " |")
    md = ["| client | slot | own txs | block txs | tau(fee→earlier) | tau(send→earlier) | price@position |", "|---|---|---|---|---|---|---|"] + rows
    md += ["", "| client | groups | txs | mean tau fee | mean tau send |", "|---|---|---|---|---|"]
    for c, a in agg.items():
        md.append(f"| {c} | {a['groups']} | {a['n']} | {sum(a['fee'])/len(a['fee']):+.2f} | {sum(a['send'])/len(a['send']):+.2f} |")
    sent = json.load(open(out + "/results.json"))
    md += ["", f"Landed {sum(1 for r in sent if r.get('landed'))}/{len(sent)}; total fees {sum(r.get('fee',0) for r in sent)} lamports"]
    open(out + "/analysis.md", "w").write("\n".join(md)); print("\n".join(md))
