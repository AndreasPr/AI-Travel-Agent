"""Synthetic harness tests; never measure real model quality."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.llm.config import load_config
from backend.llm.router import ManagedProvider
from backend.llm.types import QuotaExhausted
from eval.gate import gate
from eval.judge import Batch, LABEL, pairwise_order
from eval.judge.agreement import agreement
from eval.report import write_report
from eval.run import cached_run, evaluate, fixture_paths, validate_provenance


def test_judge_output_schema_and_range():
    score={'score':3,'reason':'Adequate synthetic example'}
    row={'id':'a','relevance':score,'coherence':score,'tone':score}
    assert Batch(judgments=[row]).judgments[0].tone.score==3
    for invalid in (0,6,True,2.5):
        with pytest.raises(ValidationError):
            Batch(judgments=[{**row,'tone':{'score':invalid,'reason':'invalid'}}])


def test_pairwise_order_is_randomized_with_seed():
    assert pairwise_order(['a','b'],7)==pairwise_order(['a','b'],7)
    assert {tuple(pairwise_order(['a','b'],i)) for i in range(20)}=={('a','b'),('b','a')}


def test_agreement_metrics_known_values():
    stats=agreement([1,2,3,4,5],[1,2,3,4,5])
    assert stats['spearman']==pytest.approx(1)
    assert stats['kappa']==pytest.approx(1)
    stats=agreement([1,2,4,5],[5,4,2,1])
    assert stats['spearman']==pytest.approx(-1)
    assert stats['kappa']==pytest.approx(-1)
    assert agreement([3,3],[3,3])['spearman'] is None


def test_runner_is_resumable(tmp_path):
    calls=[]
    async def execute():
        calls.append(1)
        return {'source':'recorded','output':{}}
    path=tmp_path/'run'/'case.json'
    first=asyncio.run(cached_run(path,'same',execute))
    assert asyncio.run(cached_run(path,'same',execute))==first
    assert len(calls)==1
    with pytest.raises(ValueError):
        asyncio.run(cached_run(path,'different',execute))


def test_runner_respects_rpd_limit():
    calls=[]
    class Counter:
        async def areserve(self,*args):
            raise QuotaExhausted('Synthetic quota exhausted')
    class Provider:
        provider='synthetic'
        model='synthetic'
        async def agenerate(self,*args,**kwargs):
            calls.append(1)
    provider=ManagedProvider(Provider(), {'limits':{'rpm':10,'tpm':None,'rpd':0}},
        {'retry':{},'max_output_tokens':5},counter=Counter(),
        bucket=SimpleNamespace(reserve=lambda x:None,refund=lambda x:None),
        retry_options={'attempts':1,'base_delay':0,'max_delay':0})
    with pytest.raises(QuotaExhausted):
        asyncio.run(provider.agenerate([]))
    assert not calls


def test_recorded_mode_never_calls_network(monkeypatch):
    import socket
    def deny(*args,**kwargs):
        raise AssertionError('Network forbidden')
    monkeypatch.setattr(socket.socket,'connect',deny)
    monkeypatch.setattr(socket,'getaddrinfo',deny)
    for path in Path('eval/fixtures/synthetic').glob('*.json'):
        assert evaluate(json.loads(path.read_text()))['checks']


def test_report_says_not_run_for_missing_models(tmp_path):
    row=evaluate(json.loads(next(Path('eval/fixtures/synthetic').glob('*.json')).read_text()))
    config=load_config()
    text=write_report([row],config,tmp_path)
    data=json.loads((tmp_path/'results.json').read_text())
    assert all(row['results']=='not run' for row in data['models'])
    assert LABEL in text
    for entry in config['evaluation']['models']:
        line=next(line for line in text.splitlines() if line.startswith('| '+entry['model']+' |'))
        assert 'not run' in line and '$0' not in line


def test_gate_fails_when_pass_rate_drops_over_2_points():
    assert not gate({'source':'synthetic','pass_rate':97.9},{'source':'synthetic','pass_rate':100})


def test_gate_passes_within_tolerance():
    assert gate({'source':'synthetic','pass_rate':98},{'source':'synthetic','pass_rate':100})


def test_synthetic_fixture_cannot_be_attributed_to_real_model():
    row=json.loads(next(Path('eval/fixtures/synthetic').glob('*.json')).read_text())
    for entry in load_config()['evaluation']['models']:
        corrupt={**deepcopy(row),**entry}
        with pytest.raises(ValueError,match='Synthetic'):
            validate_provenance(corrupt)


def test_recorded_fixtures_preferred(tmp_path):
    (tmp_path/'synthetic').mkdir()
    (tmp_path/'synthetic'/'a.json').write_text('{}')
    assert len(fixture_paths(tmp_path))==1
    (tmp_path/'recorded').mkdir()
    recorded=tmp_path/'recorded'/'b.json'
    recorded.write_text('{}')
    assert fixture_paths(tmp_path)==[recorded]


def test_calibration_refuses_synthetic_only(tmp_path,monkeypatch):
    from eval.judge.make_calibration_set import main
    monkeypatch.setattr('sys.argv',['calibration','--root',str(tmp_path)])
    with pytest.raises(SystemExit,match='no recorded runs yet; run make eval-record first'):
        main()


def test_recorded_cli_never_constructs_live_agent(tmp_path,monkeypatch):
    import socket
    import eval.report
    import eval.run
    def deny(*args,**kwargs):
        raise AssertionError('Live access forbidden')
    monkeypatch.setattr(socket.socket,'connect',deny)
    monkeypatch.setattr(socket,'getaddrinfo',deny)
    monkeypatch.setattr(eval.run,'run_live',deny)
    monkeypatch.setattr(eval.run,'fixture_paths',lambda: sorted(Path('eval/fixtures/synthetic').glob('*.json')))
    monkeypatch.setattr(eval.report,'write_report',lambda rows,config: write_report(rows,config,tmp_path/'report'))
    monkeypatch.setattr('sys.argv',['eval.run','--recorded','--limit','2','--output',str(tmp_path/'run.json')])
    eval.run.main()
    rows=json.loads((tmp_path/'run.json').read_text())
    assert len(rows)==2
    assert all(row['source']=='synthetic' for row in rows)


def test_judge_batch_is_blind_and_maps_reordered_ids():
    from eval.judge import judge_batch
    from backend.llm.types import Response
    captured=[]
    class Provider:
        def generate(self,messages,**kwargs):
            captured.extend(messages)
            score={'score':4,'reason':'Good synthetic example'}
            return Response(text=json.dumps({'judgments':[{'id':str(i),'relevance':score,'coherence':score,'tone':score} for i in range(2)]}),provider='synthetic',model='synthetic')
    rows=[{'id':str(i),'provider':'hidden-provider','model':'hidden-model','request':'Synthetic request','output':{'itinerary':{},'message':'Synthetic answer'}} for i in range(2)]
    assert set(judge_batch(Provider(),rows,seed=1))=={'0','1'}
    assert 'hidden-provider' not in json.dumps(captured)
    assert 'hidden-model' not in json.dumps(captured)


def test_gate_rejects_source_change():
    with pytest.raises(ValueError,match='source changed'):
        gate({'source':'recorded','pass_rate':100},{'source':'synthetic','pass_rate':100})


def test_judge_invalid_json_retries_with_batch_scaled_budget():
    from eval.judge import judge_batch
    from backend.llm.types import Response, InvalidOutput
    calls=[]
    score={'score':3,'reason':'Synthetic assessment'}
    class Provider:
        def generate(self,messages,**kwargs):
            calls.append((deepcopy(messages),kwargs))
            if len(calls)==1:
                raise InvalidOutput('Provider returned invalid JSON')
            return Response(text=json.dumps({'judgments':[{'id':str(i),'relevance':score,'coherence':score,'tone':score} for i in range(4)]}),provider='synthetic',model='synthetic')
    rows=[{'id':str(i),'request':'Synthetic request','output':{}} for i in range(4)]
    assert len(judge_batch(Provider(),rows))==4
    assert len(calls)==2
    assert calls[0][1]['max_output_tokens']==load_config()['evaluation']['judge']['output_tokens_per_itinerary']*4
    assert calls[0][0][:2]==calls[1][0][:2]


def test_judge_never_accepts_partial_or_out_of_range_scores():
    from eval.judge import judge_batch
    from backend.llm.types import Response, InvalidOutput
    calls=[]
    class Provider:
        def generate(self,*args,**kwargs):
            calls.append(1)
            return Response(text='{"judgments":[]}',provider='synthetic',model='synthetic')
    with pytest.raises(InvalidOutput,match='no scores saved'):
        judge_batch(Provider(),[{'id':'case','request':'Synthetic request','output':{}}])
    assert len(calls)==load_config()['evaluation']['judge']['attempts']
