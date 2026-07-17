"""Dependency-free web client served by the Mist API process."""

WEB_CLIENT_HTML = r"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Mist</title><style>
body{margin:0;font:15px system-ui;background:#0b1020;color:#e8edf7}main{max-width:960px;margin:auto;padding:24px}
input,textarea,button{font:inherit;border-radius:8px;border:1px solid #34415c;background:#141b2d;color:inherit;padding:10px}
textarea{box-sizing:border-box;width:100%;min-height:90px}button{cursor:pointer}.row{display:flex;gap:8px;margin:10px 0}.row input{flex:1}
#events{white-space:pre-wrap;background:#11182a;padding:16px;border-radius:10px;min-height:300px;overflow:auto}.muted{color:#98a6bd}
</style><main><h1>Mist</h1><p class="muted">Thin web client — decisions and tools remain on the server.</p>
<div class="row"><input id="token" type="password" placeholder="Bearer token from ~/.mist/server.json"><button id="create">New session</button></div>
<div id="status" class="muted">No session</div><div id="events"></div>
<textarea id="prompt" placeholder="What should Mist do?"></textarea><button id="send">Send</button></main><script>
let sid=null,source=null; const out=document.querySelector('#events'),status=document.querySelector('#status');
const headers=()=>({'Authorization':'Bearer '+document.querySelector('#token').value,'Content-Type':'application/json'});
document.querySelector('#create').onclick=async()=>{let r=await fetch('/session',{method:'POST',headers:headers(),body:'{}'});let j=await r.json();if(!r.ok){status.textContent=j.error;return}sid=j.id;status.textContent='Session '+sid;connect()};
async function connect(){let r=await fetch('/session/'+sid+'/events',{headers:headers()});let reader=r.body.getReader(),decoder=new TextDecoder(),buffer='';while(true){let x=await reader.read();if(x.done)break;buffer+=decoder.decode(x.value,{stream:true});let frames=buffer.split('\n\n');buffer=frames.pop();for(let frame of frames){let line=frame.split('\n').find(x=>x.startsWith('data: '));if(line){let event=JSON.parse(line.slice(6));out.textContent+=(event.type==='AgentResponseMessage'?event.data.content:JSON.stringify(event))+'\n'}}}}
document.querySelector('#send').onclick=async()=>{if(!sid)return;let prompt=document.querySelector('#prompt').value;await fetch('/session/'+sid+'/message',{method:'POST',headers:headers(),body:JSON.stringify({prompt})})};
</script></html>"""
