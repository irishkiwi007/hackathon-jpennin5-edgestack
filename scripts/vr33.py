import csv, math, io, sys, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
R = r'C:\Users\Lenovo\Downloads\TrustyRustyEngine-main\TrustyRustyEngine-main\data\historical\SPY.csv'
rows = list(csv.DictReader(open(R, encoding='utf-8')))
d = [datetime.date.fromisoformat(r['date']) for r in rows]
c = [float(r['adj_close']) for r in rows]
print(f'SPY {len(c)} sessions  {d[0]} -> {d[-1]}  ({(d[-1]-d[0]).days/365.25:.1f} years)')

def var(x):
    m = sum(x)/len(x); return sum((v-m)**2 for v in x)/(len(x)-1)

ERAS = [('dotcom+   1993-2002', datetime.date(1993,1,1), datetime.date(2002,12,31)),
        ('recovery  2003-2007', datetime.date(2003,1,1), datetime.date(2007,12,31)),
        ('GFC       2008-2012', datetime.date(2008,1,1), datetime.date(2012,12,31)),
        ('QE bull   2013-2019', datetime.date(2013,1,1), datetime.date(2019,12,31)),
        ('covid/inf 2020-2022', datetime.date(2020,1,1), datetime.date(2022,12,31)),
        ('recent    2023-2026', datetime.date(2023,1,1), datetime.date(2026,12,31)),
        ('ALL       1993-2026', datetime.date(1993,1,1), datetime.date(2026,12,31))]
print('\nVARIANCE RATIO VR(q) = Var(q-day) / (q x Var(1-day)) — by era')
print(f'{"era":<22} {"n":>6} ' + ' '.join(f'{"q="+str(q):>8}' for q in (2,5,10,21,42)))
for nm, lo, hi in ERAS:
    ix = [i for i,x in enumerate(d) if lo <= x <= hi]
    if len(ix) < 300: continue
    a,b = ix[0], ix[-1]
    r1 = [math.log(c[i]/c[i-1]) for i in range(max(a,1), b+1)]
    v1 = var(r1)
    cells = []
    for q in (2,5,10,21,42):
        rq = [math.log(c[i+q]/c[i]) for i in range(a, b-q+1)]
        cells.append(f'{var(rq)/(q*v1):>8.3f}' if len(rq) > 50 else f'{"-":>8}')
    print(f'{nm:<22} {len(ix):>6} ' + ' '.join(cells))
print("""
VR < 1 = mean reverting (multi-day variance below sqrt-t scaling)
VR > 1 = trending""")

print('\nANNUALISED DRIFT by era (the assumption the strategy leans on)')
print(f'{"era":<22} {"n":>6} {"ann drift":>11} {"ann vol":>9}')
for nm, lo, hi in ERAS:
    ix = [i for i,x in enumerate(d) if lo <= x <= hi]
    if len(ix) < 300: continue
    a,b = ix[0], ix[-1]
    yrs = (d[b]-d[a]).days/365.25
    dr = (c[b]/c[a])**(1/yrs)-1
    r1 = [math.log(c[i]/c[i-1]) for i in range(max(a,1), b+1)]
    print(f'{nm:<22} {len(ix):>6} {dr*100:>10.1f}% {math.sqrt(var(r1)*252)*100:>8.1f}%')
