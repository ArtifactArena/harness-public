"""Per-model Elo leaderboards of the 30 selected sampling bots, fitted over every pool game among those 30 (all groups)."""
import json,itertools,sys,datetime
from pathlib import Path
sys.path.insert(0,'<work-root>/iterative-length10-round-robin-20260925/tournament');from rating import fit_elo
S=Path(sys.argv[1]);sel=json.load(open(S/'sampling_bots_selected_for_final_tournament.json'))
out={'pool':'sh250-pool-5ac92bc7','selection_seed':sel['seed'],'method':'Bradley-Terry MAP per model over all pool games among its 30 selected bots (5 seeds per pairing, colors as played); draws 0.5; prior N(1000, 800^2); bots with no games have no rating','models':{}}
md=['# Sampling harness · stage 1 Elo leaderboards per model','',f"Generated {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. For each model, Elo is fitted over every SH-250 pool game between any two of its 30 selected bots (all three groups together, since all 30 come from one pool run and the pool played every eligible pairing in that run). Same estimator as the existing tournaments: Bradley-Terry MAP, draws 0.5, prior N(1000, 800²), centred at 1000 within each model. Ratings are comparable within a model only, not across models.",'',"Bots the pool did not admit (failed build, validation or the qualification round) have no games and appear at the bottom without a rating. Group winners from `sampling_stage1_results.md` are marked ★.",'']
totals=0
for model,rows in sel['selection'].items():
    run=sel['chosen_run'][model];L=json.load(open(S/model/f'g{run}'/'pool_ledger.json'));verdict={e['artifact_id']:e for e in L['ledger']}
    ids=[r['artifact_id'] for r in rows];info={r['artifact_id']:r for r in rows};st={i:dict(wins=0,losses=0,draws=0,games=0) for i in ids};results=[]
    for a,b in itertools.combinations(ids,2):
        p=S/model/f'g{run}'/'matches'/f'{a}_vs_{b}'/'match_result.json'
        if not p.exists():continue
        m=json.load(open(p));red,blue=m['red_bot'],m['blue_bot']
        for g in m['matches']:
            w=g['winner']
            if w=='red':st[red]['wins']+=1;st[blue]['losses']+=1;results.append(dict(candidate_id=red,opponent_id=blue,outcome='win'))
            elif w=='blue':st[blue]['wins']+=1;st[red]['losses']+=1;results.append(dict(candidate_id=blue,opponent_id=red,outcome='win'))
            else:st[red]['draws']+=1;st[blue]['draws']+=1;results.append(dict(candidate_id=red,opponent_id=blue,outcome='draw'))
            st[red]['games']+=1;st[blue]['games']+=1
    totals+=len(results);elo=fit_elo(ids,results) if results else {i:None for i in ids}
    stage1=json.load(open(S/'sampling_stage1_results.json'))['models'][model]['groups'];winners={gg['winner'] for gg in stage1.values() if gg['standings'][0]['eligible']}
    rated=sorted([i for i in ids if elo[i] is not None],key=lambda i:(-elo[i],info[i]['slot']));unrated=sorted([i for i in ids if elo[i] is None],key=lambda i:info[i]['slot'])
    rows_out=[]
    md.append(f'## {model}');md.append('');md.append(f"Pool run `g{run}`, {len(results)} games among {len(rated)} rated bots.");md.append('');md.append('| rank | bot | group | slot | W-L-D | games | Elo |');md.append('|--:|---|:-:|---|---|--:|--:|')
    for k,i in enumerate(rated,1):
        s=st[i];r=info[i];md.append(f"| {k} | `{i}`{' ★' if i in winners else ''} | {r['group']} | c{r['slot']:03d} | {s['wins']}-{s['losses']}-{s['draws']} | {s['games']} | {elo[i]:.1f} |");rows_out.append(dict(rank=k,id=i,group=r['group'],slot=r['slot'],**s,elo=elo[i],group_winner=i in winners))
    for i in unrated:
        r=info[i];md.append(f"| — | `{i}` | {r['group']} | c{r['slot']:03d} | no games | 0 | — ({verdict.get(i,{}).get('reason','not in ledger')}) |");rows_out.append(dict(rank=None,id=i,group=r['group'],slot=r['slot'],wins=0,losses=0,draws=0,games=0,elo=None,reason=verdict.get(i,{}).get('reason'),group_winner=False))
    md.append('');out['models'][model]={'run':f'g{run}','games':len(results),'rated_bots':len(rated),'leaderboard':rows_out}
md.insert(5,f'Totals: {totals} pool games across the 21 models.');md.insert(6,'')
Path(sys.argv[2]).write_text('\n'.join(md));Path(sys.argv[3]).write_text(json.dumps(out,indent=1));print('games',totals)
