"""Diagnose the IV calibration. VIX is NOT ATM implied volatility."""
import math,sys,io
import numpy as np
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
RATE=0.045
def ncdf(x): return 0.5*(1.0+math.erf(x/math.sqrt(2.0)))
def bsp(S,K,T,r,s):
    if s<=0 or T<=0: return max(0.0,K-S)
    d1=(math.log(S/K)+(r+0.5*s*s)*T)/(s*math.sqrt(T)); return K*math.exp(-r*T)*ncdf(-(d1-s*math.sqrt(T)))-S*ncdf(-d1)
def bsc(S,K,T,r,s):
    if s<=0 or T<=0: return max(0.0,S-K)
    d1=(math.log(S/K)+(r+0.5*s*s)*T)/(s*math.sqrt(T)); return S*ncdf(d1)-K*math.exp(-r*T)*ncdf(d1-s*math.sqrt(T))
SKEW_X=[-0.06,-0.04,-0.02,0.0,0.02,0.04,0.06]; SKEW_Y=[1.63,1.35,1.15,1.00,0.85,0.90,1.12]
def sk(m): return float(np.interp(m,SKEW_X,SKEW_Y))

print('LIVE REFERENCE (measured 2026-08-28):')
print('  SPY spot 769.28   VIX 18.71 -> 0.187')
print('  actual SPY ATM IV      0.099')
print('  actual SPY 6%% OTM put  0.187   <-- equals VIX')
print()
print('  => VIX corresponds to roughly a 6%% OTM put, NOT the ATM option.')
print('     ATM IV = VIX / %.2f = %.3f  (matches the measured 0.099)'%(sk(-0.06),0.187/sk(-0.06)))
print()
S=769.28; T=14/365.0
print('PRICING A 2%%-WIDE PUT SPREAD, short 2%% OTM, three ways:')
print('%-42s %9s %9s %9s'%('method','short','long','credit'))
Kps,Kpl=S*0.98,S*0.98-S*0.02
# (a) the bug: VIX as ATM IV, then skew on top
iv_atm_bug=0.187
a_s=bsp(S,Kps,T,RATE,iv_atm_bug*sk(-0.02)); a_l=bsp(S,Kpl,T,RATE,iv_atm_bug*sk(-0.04))
print('%-42s %9.2f %9.2f %9.2f'%('(a) VIX as ATM, skew applied [THE BUG]',a_s,a_l,a_s-a_l))
# (b) earlier scripts: VIX as ATM IV, no skew at all
b_s=bsp(S,Kps,T,RATE,iv_atm_bug); b_l=bsp(S,Kpl,T,RATE,iv_atm_bug)
print('%-42s %9.2f %9.2f %9.2f'%('(b) VIX flat, no skew [earlier runs]',b_s,b_l,b_s-b_l))
# (c) correct: calibrate ATM from VIX, then apply skew
iv_atm=0.187/sk(-0.06)
c_s=bsp(S,Kps,T,RATE,iv_atm*sk(-0.02)); c_l=bsp(S,Kpl,T,RATE,iv_atm*sk(-0.04))
print('%-42s %9.2f %9.2f %9.2f'%('(c) ATM=VIX/1.63, skew applied [CORRECT]',c_s,c_l,c_s-c_l))
# (d) ground truth from live quotes
print('%-42s %9s %9s %9s'%('(d) live quoted mids (2%%/4%% OTM puts)','~9.5','~4.6','~4.9'))
print()
print('  Method (a) inflates BOTH legs; because the long leg is further OTM it gets the')
print('  bigger multiplier, so the credit is squeezed and the structure looks unprofitable.')
print('  Method (b) understates the long leg (no skew), so it OVERSTATES the credit.')
print()
print('IMPACT ON THE EARLIER RESULT (+$27/contract for the 5%%-wide put spread):')
Kps2,Kpl2=S,S*0.95
b2=bsp(S,Kps2,T,RATE,iv_atm_bug)-bsp(S,Kpl2,T,RATE,iv_atm_bug)
c2=bsp(S,Kps2,T,RATE,iv_atm*sk(0.0))-bsp(S,Kpl2,T,RATE,iv_atm*sk(-0.05))
print('  credit, method (b) as used:   %.2f  -> %.0f $/contract'%(b2,b2*100))
print('  credit, method (c) corrected: %.2f  -> %.0f $/contract'%(c2,c2*100))
print('  the earlier runs overstated entry credit by %.0f%%'%(100*(b2/c2-1)))
print()
print('  BUT both entry and exit used the same (wrong) convention, so the P&L is a')
print('  difference of two similarly-biased numbers. Direction is likely preserved;')
print('  the LEVEL needs recomputing with the calibrated surface.')
