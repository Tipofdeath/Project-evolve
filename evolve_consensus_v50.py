"""EVOLVE 5.0 shared paper coordinator: conservative cross-engine consensus.
Consumes reports from the existing DAILY, HOURLY and MTF workflows.
Never places live orders. Missing/stale reports => no entry.
"""
import json
from pathlib import Path
from datetime import datetime,timezone
from evolve_shared import AUTO_MARKETS,metadata

OUT=Path('consensus_report_v50.json')
def read(path):
    return json.loads(Path(path).read_text())
def evaluate(daily,hourly,mtf,now=None):
    now=now or datetime.now(timezone.utc)
    d={r['symbol']:r for r in daily.get('results',[])}
    h={(r['symbol'],r['strategy']):r for r in hourly.get('results',[])}
    m={r['symbol']:r for r in mtf.get('results',[])}
    out=[]
    for sym in AUTO_MARKETS:
        reasons=[];score=0
        dr=d.get(sym);mr=m.get(sym)
        hrs=[h.get((sym,s)) for s in ('original','breakout')]
        if not dr or not mr or any(x is None for x in hrs):
            reasons.append('missing_engine_report')
        else:
            try:
                daily_day=datetime.fromisoformat(dr['last_completed_day']).replace(tzinfo=timezone.utc)
                mtf_time=datetime.fromisoformat(mr['last_15m_utc'])
                hourly_times=[datetime.fromisoformat(x['last_hour_utc']) for x in hrs]
                if (now-daily_day).total_seconds()>72*3600 or daily_day>now:reasons.append('stale_daily')
                if (now-mtf_time).total_seconds()>3600 or mtf_time>now:reasons.append('stale_mtf')
                if any((now-t).total_seconds()>3*3600 or t>now for t in hourly_times):
                    reasons.append('stale_hourly')
                if daily.get('errors') or hourly.get('errors') or mtf.get('errors'):
                    reasons.append('engine_errors')
                # MTF signal is the trigger, daily and hourly are contextual confirmation.
                if mr.get('entry_signal') is True:score+=2
                else:reasons.append('no_15m_trigger')
                if dr.get('original_signal') is True or dr.get('breakout_signal') is True:score+=1
                else:reasons.append('daily_not_confirmed')
                # Use a fresh hourly directional signal, not whether another paper bot holds a position.
                # Older reports without this field cannot confirm an entry.
                if all(isinstance(x.get('signal_active'),bool) for x in hrs) and any(x['signal_active'] for x in hrs):
                    score+=1
                else:reasons.append('hourly_not_confirmed')
            except (ValueError,TypeError,KeyError) as e:
                reasons.append('invalid_timestamp_or_fields')
        # This is a research recommendation only. Never treat it as an executable order.
        qualified=score>=3 and 'no_15m_trigger' not in reasons and not any(
            x in reasons for x in ('missing_engine_report','stale_daily','stale_mtf',
                                  'stale_hourly','engine_errors','invalid_timestamp_or_fields'))
        out.append({'symbol':sym,'confirmation_score':score,'max_score':4,
                    'paper_entry_candidate':qualified,'reasons':reasons})
    return out

def run():
    report={'version':'5.0-consensus','integration':metadata('shared-consensus-paper'),
       'mode':'signal consensus only; no orders or portfolio changes',
       'approved_for_trading':False,'evaluated_at':datetime.now(timezone.utc).isoformat()}
    try:
        report['results']=evaluate(read('forward_report_v45.json'),
            read('hourly_report_v48.json'),read('mtf_report_v49.json'))
        report['errors']=[]
    except (OSError,ValueError,KeyError,TypeError) as exc:
        report['results']=[];report['errors']=[str(exc)]
    OUT.write_text(json.dumps(report,indent=2)+'\n')
    return 0 if not report['errors'] else 1
if __name__=='__main__':raise SystemExit(run())
