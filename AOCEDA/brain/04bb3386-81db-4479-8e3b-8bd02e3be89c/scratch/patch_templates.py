import os

file_path = r"c:\Users\silve\Desktop\MEMOIRE\AOCEDA\templates\aoceda-ia.html"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Locate the script tag block
start_tag = '<script type="text/babel">'
end_tag = '</script>'

start_idx = content.find(start_tag)
end_idx = content.find(end_tag, start_idx) + len(end_tag)

if start_idx == -1 or end_idx == -1:
    print("Error: script tags not found!")
    exit(1)

new_script = """<script type="text/babel">
const {useState,useEffect,useRef} = React;

// --- Authentication helper ---
const token = localStorage.getItem('aoceda_access_token');
if (!token && window.location.pathname.indexOf('aoceda-auth.html') === -1) {
  window.location.href = 'aoceda-auth.html';
}

function fetchWithAuth(url, options = {}) {
  const token = localStorage.getItem('aoceda_access_token');
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    ...(options.headers || {})
  };
  return fetch(url, { ...options, headers }).then(res => {
    if (res.status === 401) {
      localStorage.removeItem('aoceda_access_token');
      localStorage.removeItem('aoceda_refresh_token');
      window.location.href = 'aoceda-auth.html';
      throw new Error('Non autorisé');
    }
    return res;
  });
}

function Logo({s=28}){return<svg width={s} height={s} viewBox="0 0 36 36" fill="none"><rect width="36" height="36" rx="8" fill="#C9760E"/><path d="M5 18H10L13.5 9L17.5 27L21 14L24 22L27 18H31" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/></svg>;}

function TToggle({theme,onToggle}){
  return<button className="icon-btn" onClick={onToggle} aria-label="Changer thème">
    {theme==='light'
      ?<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
      :<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>}
  </button>;
}

/* ── Context Panel ── */
function CtxPanel({quota, user, kpis}){
  const billing = kpis ? kpis.facture_estimee_fcfa : 23490;
  const activeAlerts = kpis ? kpis.alertes_actives : 2;
  const currentConso = kpis ? `${kpis.consommation_jour_kwh} kWh (Jour)` : '142 kWh';
  
  const rows=[
    {l:'Consommation',v: currentConso,cls:''},
    {l:'Tarif CIE',v:'87 FCFA/kWh',cls:'accent'},
    {l:'Ampérage',v: user ? `${user.amperage_souscrit || '15A'}` : '15A — Général',cls:''},
    {l:'Type compteur',v: user ? `${user.type_compteur || 'Prépayé'}` : 'Prépayé',cls:''},
    {l:'Facture estimée',v:`${billing.toLocaleString('fr-FR')} FCFA`,cls:'accent'},
    {l:'Alertes actives',v:`${activeAlerts}`,cls: activeAlerts > 0 ? 'err' : 'ok'},
    {l:'Pic max',v:'2 340 W',cls: activeAlerts > 0 ? 'err' : ''},
  ];
  
  return<div className="ctx-panel">
    <div className="ctx-header">Données transmises à l'IA</div>
    <div className="ctx-body">
      <div className="ctx-section">
        <div className="ctx-sec-title">Contexte IoT — temps réel</div>
        {rows.map((r,i)=><div key={i} className="ctx-row">
          <span className="ctx-lbl">{r.l}</span>
          <span className={`ctx-val ${r.cls}`}>{r.v}</span>
        </div>)}
      </div>
      <div className="privacy-badge">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{flexShrink:0}}><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
        <span>Données anonymisées — aucun identifiant personnel ou clé privée n'est partagé.</span>
      </div>
      <div className="quota-wrap">
        <div className="quota-row">
          <span className="quota-lbl">Requêtes aujourd'hui</span>
          <span className="quota-val">{10 - quota}/10</span>
        </div>
        <div className="quota-bar"><div className="quota-fill" style={{width:`${(10 - quota)*10}%`}}/></div>
      </div>
    </div>
  </div>;
}

/* ── Message text renderer (handles **bold** and line breaks) ── */
function MsgText({text}){
  const lines=text.split('\\n');
  return<>{lines.map((line,li)=>{
    if(!line.trim())return<br key={li}/>;
    const parts=line.split(/(\*\*[^*]+\*\*)/g);
    const isNum=/^\d+\\./.test(line.trim());
    const content=parts.map((p,pi)=>
      p.startsWith('**')&&p.endsWith('**')
        ?<strong key={pi}>{p.slice(2,-2)}</strong>
        :<span key={pi}>{p}</span>
    );
    if(isNum)return<p key={li} style={{marginBottom:'5px'}}>{content}</p>;
    return<p key={li}>{content}</p>;
  })}</>;
}

const SUGGESTIONS=["Mon appareil le plus consommateur ?","Donne-moi des conseils pour la clim","Quand devrais-je couper ma veille nocturne ?","Que signifie le tarif de 87 FCFA de la CIE ?"];

function TypingBubble(){
  return<div className="typing-row">
    <div className="msg-avatar av-ai"><Logo s={16}/></div>
    <div className="typing-bubble">
      <div className="tydot"/><div className="tydot"/><div className="tydot"/>
    </div>
  </div>;
}

function ChatArea({quota, setQuota, user}){
  const [msgs,setMsgs]=useState([
    {role:'ai',text:"Bonjour ! Je suis votre **Assistant Énergie AOCEDA**.\\n\\nJe suis configuré pour vous aider à réduire votre consommation électrique sous le tarif CIE de **87 FCFA/kWh**. Comment puis-je vous aider aujourd'hui ?",time:'14h25'}
  ]);
  const [input,setInput]=useState('');
  const [typing,setTyping]=useState(false);
  const [depleted,setDepleted]=useState(false);
  const endRef=useRef(null);
  const taRef=useRef(null);
  
  useEffect(()=>{endRef.current?.scrollIntoView({behavior:'smooth'});},[msgs,typing]);
  
  const autoResize=()=>{const t=taRef.current;if(t){t.style.height='auto';t.style.height=Math.min(t.scrollHeight,120)+'px';}};
  
  const send=(txt)=>{
    if(!txt.trim()||typing||depleted)return;
    const newMsg={role:'user',text:txt.trim(),time:new Date().toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})};
    setMsgs(m=>[...m,newMsg]);setInput('');
    if(taRef.current)taRef.current.style.height='auto';
    setTyping(true);

    fetchWithAuth('/api/assistant/chat/', {
      method: 'POST',
      body: JSON.stringify({ message: txt.trim() })
    })
    .then(async res => {
      const data = await res.json();
      if (!res.ok) {
        if (res.status === 429) {
          setDepleted(true);
        }
        throw new Error(data.detail || 'Une erreur est survenue.');
      }
      return data;
    })
    .then(data => {
      setQuota(10 - data.nb_requetes_aujourd_hui);
      setMsgs(m=>[...m,{
        role:'ai',
        text: data.response,
        time: new Date().toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})
      }]);
      setTyping(false);
    })
    .catch(err => {
      setMsgs(m=>[...m,{
        role:'ai',
        text: `Désolée, je rencontre un problème de connexion : ${err.message}`,
        time: new Date().toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})
      }]);
      setTyping(false);
    });
  };

  const handleKey=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send(input);}};
  
  return<div className="chat-panel">
    <div className="messages">
      {msgs.map((m,i)=><div key={i} className={`msg-row ${m.role}`}>
        <div className={`msg-avatar ${m.role==='ai'?'av-ai':'av-user'}`}>{m.role==='ai'?<Logo s={14}/>:(user ? user.nom.substring(0, 2).toUpperCase() : 'AK')}</div>
        <div>
          <div className={`msg-bubble ${m.role}`}><MsgText text={m.text}/></div>
          <div className={`msg-time ${m.role==='ai'?'ai-t':''}`}>{m.role==='ai'?'Assistant AOCEDA · ':'Vous · '}{m.time}</div>
        </div>
      </div>)}
      {typing&&<TypingBubble/>}
      <div ref={endRef}/>
    </div>
    {!depleted&&<div className="suggestions">
      {SUGGESTIONS.map((s,i)=><button key={i} className="sug-chip" onClick={()=>send(s)}>{s}</button>)}
    </div>}
    {depleted
      ?<div className="quota-empty"><strong>Limite journalière atteinte (10/10)</strong>L'assistant a répondu à 10 messages aujourd'hui. Vous pourrez lui poser d'autres questions demain !</div>
      :<div className="input-bar">
        <div className="input-wrap">
          <textarea ref={taRef} className="msg-textarea" rows="1" value={input}
            onChange={e=>{setInput(e.target.value);autoResize();}}
            onKeyDown={handleKey} placeholder="Posez votre question sur votre consommation…"/>
          <button className="send-btn" onClick={()=>send(input)} disabled={!input.trim()||typing}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
          </button>
        </div>
        <div className="input-footer">
          <span className="input-hint">Entrée pour envoyer · Maj+Entrée pour aller à la ligne</span>
          <span className="quota-inline">{quota} question{quota > 1 ? 's' : ''} restante{quota > 1 ? 's' : ''} aujourd'hui</span>
        </div>
      </div>}
  </div>;
}

function App(){
  const [theme,setTheme]=useState(()=>localStorage.getItem('aoceda-theme')||'light');
  const [quota,setQuota]=useState(10);
  const [user, setUser]=useState(null);
  const [kpis, setKpis]=useState(null);

  useEffect(()=>{document.documentElement.setAttribute('data-theme',theme);localStorage.setItem('aoceda-theme',theme);},[theme]);

  useEffect(() => {
    fetchWithAuth('/api/users/me/')
      .then(res => res.json())
      .then(data => setUser(data))
      .catch(err => console.error(err));

    fetchWithAuth('/api/analytics/summary/')
      .then(res => res.json())
      .then(data => setKpis(data))
      .catch(err => console.error(err));

    // Get current IA conversation request count to set quota
    fetchWithAuth('/api/assistant/chat/', { method: 'POST', body: JSON.stringify({ message: 'AOCEDA_INIT_CHECK' }) })
      .then(async res => {
        const data = await res.json();
        if (data.nb_requetes_aujourd_hui !== undefined) {
          setQuota(10 - data.nb_requetes_aujourd_hui);
        }
      })
      .catch(err => console.error(err));
  }, []);

  return<div style={{display:'flex',flexDirection:'column',height:'100%'}}>
    <div className="topbar">
      <a href="aoceda-dashboard.html" className="back-btn">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6"/></svg>
        Tableau de bord
      </a>
      <div className="sep"/>
      <span className="topbar-title">Assistant IA — Énergie AOCEDA</span>
      <div className="topbar-actions">
        <span style={{fontSize:'12px',color:'var(--tx-m)',padding:'0 8px'}}>{quota}/10 questions</span>
        <TToggle theme={theme} onToggle={()=>setTheme(t=>t==='light'?'dark':'light')}/>
      </div>
    </div>
    <div className="ai-layout">
      <CtxPanel quota={quota} user={user} kpis={kpis}/>
      <ChatArea quota={quota} setQuota={setQuota} user={user}/>
    </div>
  </div>;
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
</script>"""

new_content = content[:start_idx] + new_script + content[end_idx:]

with open(file_path, "w", encoding="utf-8") as f:
    f.write(new_content)

print("Template patched successfully!")
