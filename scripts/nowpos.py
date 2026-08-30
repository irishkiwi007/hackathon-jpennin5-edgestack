import csv, math, io, sys, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
R = r'C:\Users\Lenovo\Downloads\TrustyRustyEngine-main\TrustyRustyEngine-main\data\historical\SPY.csv'
rows = list(csv.DictReader(open(R, encoding='utf-8')))
c = [float(r['adj_close']) for r in rows]
d = [datetime.date.fromisoformat(r['date']) for r in rows]
lr = [math.log(c[i]/c[i-1]) for i in range(1,len(c))]
ANN = math.sqrt(252)
def rv(i,w=20):
    s = lr[i-w:i]
    m = sum(s)/len(s)
    return math.sqrt(sum((x-m)**2 for x in s)/(len(s)-1))*ANN
series = [(d[i], rv(i)) for i in range(21, len(c))]
vals = sorted(x[1] for x in series)
CUR = 0.1040   # measured on Alpaca data to 2026-08-28
pct = sum(1 for v in vals if v <= CUR)/len(vals)*100
print(f'33-year RV20 distribution, n={len(vals)}')
print(f'  min {vals[0]*100:.1f}%  p10 {vals[len(vals)//10]*100:.1f}%  '
      f'median {vals[len(vals)//2]*100:.1f}%  p90 {vals[9*len(vals)//10]*100:.1f}%  '
      f'max {vals[-1]*100:.1f}%')
print(f'\nCURRENT RV20 = {CUR*100:.2f}%  ->  {pct:.1f}th percentile of 33 years')
# what happened next, historically, from this vol band
band = [(dt,v) for dt,v in series if abs(v-CUR)/CUR < 0.12]
print(f'\nhistorical windows within +/-12% of current vol: {len(band)}')
FWD = 21
idx = {dt:i for i,dt in enumerate(d)}
fwd = []
for dt,v in band:
    i = idx[dt]
    if i+FWD < len(c)-1 and i+FWD < len(lr):
        f = rv(i+FWD)
        if f: fwd.append((v,f, c[i+FWD]/c[i]-1))
if fwd:
    mv = sum(x[0] for x in fwd)/len(fwd)
    mf = sum(x[1] for x in fwd)/len(fwd)
    up = sum(1 for x in fwd if x[1] > x[0])/len(fwd)*100
    ret = sum(x[2] for x in fwd)/len(fwd)*100
    print(f'  mean trailing {mv*100:.1f}%  ->  mean forward {mf*100:.1f}%  (ratio {mf/mv:.3f})')
    print(f'  forward vol ROSE in {up:.1f}% of them')
    print(f'  mean forward 21d SPY return: {ret:+.2f}%')
