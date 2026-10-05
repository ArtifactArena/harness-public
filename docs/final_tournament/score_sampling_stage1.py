"""Stage 1 of the final tournament for the sampling harness, assembled entirely from the SH-250 pool's existing
Top-Bot-per-Run round-robin results (5 seeds per pairing, colors as played). No new matches."""
import json,itertools,collections,os,sys,datetime
from pathlib import Path
sys.path.insert(0,'<work-root>/iterative-length10-round-robin-20260925/tournament');from rating import fit_elo
S=Path(sys.argv[1]);sel=json.load(open(S/'sampling_bots_selected_for_final_tournament.json'))
POOL='sh250-pool-5ac92bc7';out={'pool':POOL,'selection_seed':sel['seed'],'games_per_pairing':5,'winner_rule':'points (win 1, draw 0.5) over all 45 pairings incl. forfeits, then wins, then lower slot','forfeit_rule':'a bot the pool did not admit (not eligible in pool_ledger.json) has no games; each of its pairings counts as 5 forfeit wins for an eligible opponent, and as no games when both are ineligible','models':{}}
md=['# Sampling harness · stage 1 results (final tournament)','',f"Assembled {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from the SH-250 pool `{POOL}` Top-Bot-per-Run round robin (`pool_rr/<model>/g<run>/matches/*/match_result.json`, 5 seeds per pairing, 300 s, colors as played). No new matches were simulated.",'',f"Bots: `sampling_bots_selected_for_final_tournament.md` (seed {sel['seed']}): 21 models × 3 groups of 10, each model's 30 bots drawn from one 50-slot pool run.",'',f"Winner rule per group: {out['winner_rule']}. Forfeits: {out['forfeit_rule']}. Bradley-Terry Elo (the existing MAP estimator, draws 0.5, prior N(1000, 800²)) is fitted per group over simulated games only and shown for reference.",'']
tot_sim=tot_forf=0;winners=[]
for model,rows in sel['selection'].items():
    run=sel['chosen_run'][model];L=json.load(open(S/model/f'g{run}'/'pool_ledger.json'));verdict={e['artifact_id']:e for e in L['ledger']}
    out['models'][model]={'run':f'g{run}','slot_range':L['slot_range'],'pool_git_sha':L['git_sha'],'config_md5':L['config_md5'],'groups':{}}
    md.append(f'## {model}');md.append('');md.append(f"Pool run `g{run}` (slots {L['slot_range'][0]:03d}-{L['slot_range'][1]-1:03d}), harness `{L['git_sha'][:7]}`, tournament config md5 `{L['config_md5']}`.");md.append('')
    for g in ('1','2','3'):
        bots=[r for r in rows if r['group']==g];ids=[r['artifact_id'] for r in bots];slot={r['artifact_id']:r['slot'] for r in bots}
        st={i:dict(id=i,slot=slot[i],eligible=bool(verdict.get(i,{}).get('eligible')),reason=verdict.get(i,{}).get('reason','not in ledger'),wins=0,losses=0,draws=0,forfeit_wins=0,forfeit_losses=0,points=0.0,games=0) for i in ids}
        results=[];sim=forf=missing=0
        for a,b in itertools.combinations(ids,2):
            p=S/model/f'g{run}'/'matches'/f'{a}_vs_{b}'/'match_result.json'
            if p.exists():
                m=json.load(open(p));red,blue=m['red_bot'],m['blue_bot'];assert {red,blue}=={a,b}
                for game in m['matches']:
                    w=game['winner'];sim+=1
                    if w=='red':wb,lb=red,blue
                    elif w=='blue':wb,lb=blue,red
                    else:wb=lb=None
                    if wb:st[wb]['wins']+=1;st[lb]['losses']+=1;st[wb]['points']+=1;results.append(dict(candidate_id=wb,opponent_id=lb,outcome='win'))
                    else:
                        for x in (red,blue):st[x]['draws']+=1;st[x]['points']+=.5
                        results.append(dict(candidate_id=red,opponent_id=blue,outcome='draw'))
                    st[red]['games']+=1;st[blue]['games']+=1
            else:
                ea,eb=st[a]['eligible'],st[b]['eligible']
                if ea and eb:missing+=1
                elif ea:st[a]['forfeit_wins']+=5;st[a]['points']+=5;st[b]['forfeit_losses']+=5;forf+=5
                elif eb:st[b]['forfeit_wins']+=5;st[b]['points']+=5;st[a]['forfeit_losses']+=5;forf+=5
        elo=fit_elo(ids,results) if results else {i:None for i in ids}
        for i in ids:st[i]['elo']=elo[i]
        order=sorted(ids,key=lambda i:(-st[i]['points'],-st[i]['wins'],st[i]['slot']));win=order[0]
        tot_sim+=sim;tot_forf+=forf
        out['models'][model]['groups'][g]={'bots':ids,'winner':win,'simulated_games':sim,'forfeit_games':forf,'missing_eligible_pairings':missing,'standings':[st[i] for i in order]}
        winners.append((model,g,win,st[win]))
        md.append(f'### Group {g} — winner `{win}`');md.append('');md.append(f'{sim} simulated games, {forf} forfeit games'+(f', {missing} eligible pairings missing from the pool' if missing else '')+'.');md.append('');md.append('| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |');md.append('|--:|---|---|:-:|---|--:|--:|--:|')
        for k,i in enumerate(order,1):
            s=st[i];md.append(f"| {k} | `{i}` | c{s['slot']:03d} | {'yes' if s['eligible'] else 'no · '+s['reason']} | {s['wins']}-{s['losses']}-{s['draws']} | {s['forfeit_wins']} | {s['points']:.1f} | {s['elo'] if s['elo'] is not None else '—'} |")
        md.append('')
summary=['## Group winners (63)','','| model | group | winner | slot | W-L-D | forfeit W | points |','|---|:-:|---|---|---|--:|--:|']
for model,g,win,s in winners:summary.append(f"| {model} | {g} | `{win}` | c{s['slot']:03d} | {s['wins']}-{s['losses']}-{s['draws']} | {s['forfeit_wins']} | {s['points']:.1f} |")
md=md[:7]+[f'Totals: {tot_sim} simulated games reused, {tot_forf} forfeit games, {len(winners)} group winners advance to stage 2.','']+summary+['']+md[7:]
out['totals']={'simulated_games':tot_sim,'forfeit_games':tot_forf,'winners':[dict(model=m,group=g,winner=w) for m,g,w,_ in winners]}
Path(sys.argv[2]).write_text('\n'.join(md));Path(sys.argv[3]).write_text(json.dumps(out,indent=1))
print(json.dumps(dict(simulated=tot_sim,forfeits=tot_forf,winners=len(winners),eligible_winners=sum(1 for *_ ,s in winners if s['eligible']))))
