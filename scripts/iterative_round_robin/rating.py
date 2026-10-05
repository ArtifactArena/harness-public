"""The existing iterative leaderboard Elo estimator."""
import math
import numpy as np
from scipy.optimize import minimize

def fit_elo(ids, results):
    """Batch Bradley-Terry Elo MAP, centered at 1000; draws are half a win."""
    if not results:return {ident:None for ident in ids}
    index={ident:i for i,ident in enumerate(ids)};n=len(ids);k=math.log(10)/400;variance=800.**2
    a=np.array([index[r['candidate_id']] for r in results]);b=np.array([index[r['opponent_id']] for r in results])
    scores=np.array([1. if r['outcome']=='win' else 0. if r['outcome']=='loss' else .5 for r in results])
    def objective(x):
        diff=k*(x[a]-x[b]);loss=np.logaddexp(0,diff).sum()-np.dot(scores,diff)+np.dot(x-1000,x-1000)/(2*variance)
        probability=1/(1+np.exp(-diff));g=(x-1000)/variance
        np.add.at(g,a,k*(probability-scores));np.add.at(g,b,-k*(probability-scores));return loss,g
    fit=minimize(objective,np.full(n,1000.),jac=True,method='L-BFGS-B',options={'ftol':1e-12,'gtol':1e-9,'maxiter':1000})
    if not fit.success:raise RuntimeError('Elo fit failed: '+fit.message)
    played=set(a)|set(b)
    return {ident:round(float(fit.x[i]),1) if i in played else None for i,ident in enumerate(ids)}
