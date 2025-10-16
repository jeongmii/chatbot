(function(){
  const qs = new URLSearchParams(location.search);
  const pid = qs.get('pid') || qs.get('participant_id') || '';
  const studyId = qs.get('study_id') || '';
  const source = qs.get('source') || 'qualtrics_iframe';
  const sys = qs.get('sys') || '';
  const meta = qs.get('meta') || '';

  const messagesEl = document.getElementById('messages');
  const formEl = document.getElementById('composerForm');
  const inputEl = document.getElementById('composerInput');
  const sendBtn = document.getElementById('sendBtn');
  const sessionPill = document.getElementById('sessionPill');

  let ws; let connected=false; let sessionId=null; let streamingEl=null; let streamingText='';
  let awaitingAssistant=false;

  function autogrow(){
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + 'px';
  }
  inputEl.addEventListener('input', autogrow);
  autogrow();

  function createBubble(role, text){
    const div = document.createElement('div');
    div.className = 'bubble ' + role;
    div.textContent = text || '';
    messagesEl.appendChild(div);
    scrollBottom();
    return div;
  }

  function addTyping(){
    const d = document.createElement('div');
    d.className = 'bubble assistant';
    const t = document.createElement('span');
    t.className = 'typing';
    t.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
    d.appendChild(t);
    messagesEl.appendChild(d);
    scrollBottom();
    return d;
  }

  function scrollBottom(){
    messagesEl.scrollTop = messagesEl.scrollHeight + 200;
  }

  function connect(){
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    const qp = new URLSearchParams();
    if(pid) qp.set('pid', pid);
    if(studyId) qp.set('study_id', studyId);
    if(source) qp.set('source', source);
    if(sys) qp.set('sys', sys);
    if(meta) qp.set('meta', meta);

    ws = new WebSocket(`${scheme}://${location.host}/ws/chat?${qp.toString()}`);

    ws.onopen = () => { connected=true; };
    ws.onclose = () => { connected=false; };

    ws.onmessage = (ev) => {
      try { var data = JSON.parse(ev.data); } catch { return; }
      if(data.type === 'session_info'){
        sessionId = data.session_id;
        if(sessionPill){ sessionPill.textContent = sessionId; }
      } else if(data.type === 'history'){
        (data.messages || []).forEach(m => {
          const role = m.role === 'assistant' ? 'assistant' : (m.role === 'user' ? 'user' : 'assistant');
          createBubble(role, m.content || '');
        });
      } else if(data.type === 'assistant_delta'){
        if(!streamingEl){
          streamingEl = createBubble('assistant', '');
          streamingText='';
        }
        streamingText += data.delta || '';
        streamingEl.textContent = streamingText;
        scrollBottom();
      } else if(data.type === 'assistant_complete'){
        streamingEl = null; streamingText=''; awaitingAssistant=false; sendBtn.disabled=false; inputEl.disabled=false; inputEl.focus();
      } else if(data.type === 'error'){
        const e = createBubble('assistant', '에러: ' + (data.message || 'unknown'));
        e.style.background = '#7f1d1d';
        awaitingAssistant=false; sendBtn.disabled=false; inputEl.disabled=false;
      } else if(data.type === 'pong'){
        // ignore
      }
    };
  }

  connect();

  // keepalive
  setInterval(() => {
    try{ if(connected) ws.send(JSON.stringify({type:'ping'})); }catch{}
  }, 20000);

  formEl.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = (inputEl.value || '').trim();
    if(!text || !connected || awaitingAssistant) return;

    createBubble('user', text);
    inputEl.value=''; autogrow();
    awaitingAssistant=true; sendBtn.disabled=true; inputEl.disabled=true;

    try{
      ws.send(JSON.stringify({ type: 'user_message', content: text }));
    }catch(err){
      createBubble('assistant', '전송 실패: ' + (err?.message||String(err)));
      awaitingAssistant=false; sendBtn.disabled=false; inputEl.disabled=false;
    }
  });
})();
