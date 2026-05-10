import React, {useEffect, useMemo, useState} from 'react';
import {createRoot} from 'react-dom/client';
import ReactFlow, {Background, Controls, MiniMap} from 'reactflow';
import 'reactflow/dist/style.css';
import './style.css';

const archives = ['simple_tool_session', 'code_edit_session', 'tampered_session'];

function icon(t){return {judgment:'⚖️',delegation:'🔁',verification:'✅',termination:'⏹️'}[t] || '•'}

function App(){
  const [archive,setArchive]=useState('simple_tool_session');
  const [data,setData]=useState(null);
  const [selected,setSelected]=useState(null);
  useEffect(()=>{fetch(`/api/archive?path=examples/archives/${archive}.jsonl`).then(r=>r.json()).then(d=>{setData(d);setSelected(null)})},[archive]);
  const bad = new Set(data?.verification?.tampered_events || []);
  const flow = useMemo(()=>{
    const graph=data?.replay?.lineage_graph || {nodes:[],edges:[]};
    return {
      nodes: graph.nodes.map((n,i)=>({id:n.id, position:{x:(i%6)*190,y:Math.floor(i/6)*120}, data:{label:`${n.id}\n${n.type}`}, className:n.type})),
      edges: graph.edges.map((e,i)=>({id:`e-${i}`, source:e.source, target:e.target, label:e.label, animated:e.label==='delegated'}))
    };
  },[data]);
  return <div className="app">
    <aside><h2>Sessions</h2>{archives.map(a=><button key={a} className={archive===a?'active':''} onClick={()=>setArchive(a)}>{a}</button>)}<h3>Replay Integrity: <span className={data?.verification?.valid?'pass':'fail'}>{data?.verification?.valid?'PASS':'FAIL'}</span></h3><p>{data?.verification?.failure_codes?.join(', ') || 'No failures'}</p></aside>
    <main><h2>Replay Timeline</h2>{data?.replay?.timeline?.map((e,i)=><div key={e.event_id} onClick={()=>setSelected(data.events[i])} className={`event ${bad.has(e.event_id)?'tampered':e.status}`}><b>{icon(e.event_type)} {e.verb} {e.event_type}</b><span>{e.verification_state}</span><p>{e.actor} → {e.tool_name || 'session'}</p><small>{e.action}</small><code>{e.event_hash}</code></div>)}</main>
    <section className="inspector"><h2>Event Inspector</h2><pre>{selected?JSON.stringify(selected,null,2):'Click an event.'}</pre></section>
    <section className="graph"><h2>Lineage Graph</h2><ReactFlow nodes={flow.nodes} edges={flow.edges} fitView><MiniMap/><Controls/><Background/></ReactFlow></section>
  </div>
}

createRoot(document.getElementById('root')).render(<App/>);
