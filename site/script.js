const state = { selectedSearch: 0 };
const content = document.querySelector('#content');
const toc = document.querySelector('#toc nav');
const sidebar = document.querySelector('#sidebar');
const dialog = document.querySelector('#search-dialog');
const searchInput = document.querySelector('#search-input');
const searchResults = document.querySelector('#search-results');
const toast = document.querySelector('#toast');
const API = window.API_DATA || { modules: [], symbolCount: 0 };
document.querySelector('.version-row option').textContent = `v${API.version || 'development'}`;

const esc = (value='') => String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const slug = (value) => value.toLowerCase().replaceAll('_','-').replace(/[^a-z0-9-]/g,'');
const moduleByName = (name) => API.modules.find((module) => module.name === name);
const symbolByName = (module, name) => moduleByName(module)?.symbols.find((symbol) => symbol.name === name);
const MODULE_GUIDES={quantvolt:'quickstart',models:'models',numerics:'numerics',curves:'curves',pricing:'pricing',portfolio:'portfolio-risk',risk:'portfolio-risk',hedging:'hedging',assets:'assets',curvemodels:'curve-models',stats:'statistics',market:'market-utils',workflow:'workflow-guide',data:'data',exceptions:'errors',testing:'testing'};

function renderModuleNav() {
  document.querySelector('#module-nav').innerHTML = API.modules.map((module) => `<details class="nav-group"><summary><a href="#/api/${module.name}"><code>${module.name}</code><span>${module.symbols.length}</span></a></summary><div>${module.symbols.map((symbol)=>`<a href="#/api/${module.name}/${encodeURIComponent(symbol.name)}"><small class="nav-kind ${symbol.kind}"></small><code>${esc(symbol.name)}</code></a>`).join('')}</div></details>`).join('');
}

const GUIDE_NAV = [
  // Quickstart-adjacent: read these first.
  ['conventions','Conventions',[['units','Units'],['position-sign','Position signs'],['time','Dates & intervals'],['randomness','Randomness'],['precision','Tolerances']]],
  ['validation','External validation',[['black76','Black-76 vs QuantLib'],['capfloor','Cap/floor strip'],['spread','Spread options'],['mc-convergence','MC convergence'],['caveats','Caveats & limits']]],
  ['end-to-end','End-to-end tutorials',[['tutorial-map','Tutorial map'],['curve-to-var','Curve to VaR'],['reproducibility','Reproducibility']]],
  ['tutorial-spark','Tutorial: spark spread to hedge',[['setup','Clean spark spread'],['spread-option','Spread option'],['tolling-position','Tolling position'],['hedge','Variance-min hedge']]],
  ['tutorial-ppa','Tutorial: renewable PPA to CFaR',[['weather','Weather'],['scenarios','Scenarios'],['settlement','Settlement with terms'],['cfar','CFaR']]],
  ['tutorial-storage','Tutorial: storage intrinsic to hedge',[['curve','Seasonal curve'],['intrinsic','Intrinsic'],['extrinsic','Extrinsic'],['forward-hedge','Forward hedge']]],
  // Domain guides.
  ['models','Domain models',[['commodities','Commodities & hubs'],['periods','Periods & schedules'],['curves-models','Curve models'],['volatility-models','Volatility surfaces'],['instruments-models','Instruments'],['physical-models','Physical contracts'],['serialization-models','Serialization']]],
  ['curves','Forward curves',[['construction','Construction'],['interpolation','Interpolation'],['arbitrage','Cost-of-carry checks'],['models','Stochastic models']]],
  ['pricing','Pricing derivatives',[['futures','Futures'],['forwards','Forwards'],['swaps','Swaps'],['vanilla','Vanilla options'],['caps-floors','Caps & floors'],['exotics','Exotic options'],['spread-options','Spread options'],['spreads','Physical spreads'],['tolling','Tolling agreements'],['rights','Transmission rights'],['implied-vol','Implied volatility'],['mark-to-market','Mark to market']]],
  ['portfolio-risk','Portfolio & risk',[['instruments','Create instruments'],['positions','Create positions'],['market-data','Market data'],['valuation','Valuation'],['risk-engine','Risk engine'],['stress','Stress scenarios'],['delta-aggregation','Delta aggregation'],['parametric-risk','Parametric VaR'],['covariance-risk','Covariance'],['cfar-risk','CFaR'],['credit-risk','Credit VaR']]],
  ['ppa','PPAs & settlement',[['contract','Contract'],['settlement','Interval data'],['financial-ppa','Physical vs CfD'],['hedges','Power hedges'],['portfolio-settlement','Portfolio settlement'],['nomination','Nomination'],['validation-ppa','Validation']]],
  ['assets','Physical assets',[['plant','Thermal plant'],['stochastic','Stochastic dispatch'],['storage','Gas storage'],['governance','Governance']]],
  ['hedging','Hedging',[['variance','Variance minimum'],['cross','Cross-commodity'],['decomposed-delta','Decomposed delta'],['mean-variance','Mean-variance'],['ppa-nomination','PPA objectives'],['walk-forward','Walk forward']]],
  ['curve-models','Stochastic curve models',[['schwartz-smith','Schwartz–Smith'],['ss-simulation','Factor simulation'],['multifactor','Multifactor model'],['induced','Induced covariance'],['model-simulation','Forward simulation'],['power-warning','Power warning']]],
  ['rust-monte-carlo','Rust & Monte Carlo',[['native-architecture','Architecture'],['native-build','Build & install'],['asian-native','Asian MC'],['ou-native','OU simulation'],['correlated-native','Correlated forwards'],['term-native','Term structure'],['mc-var-native','Monte Carlo VaR'],['mc-validation','Validation & errors'],['mc-performance','Performance']]],
  ['data','Data & datasets',[['dataset-catalog','Optional datasets'],['dataset-fetch','Fetch & verify'],['dataset-cache','Cache & offline'],['providers','Providers'],['fetch','Provider mapping'],['snapshots','Snapshots']]],
  ['errors','Errors & validation',[['hierarchy','Hierarchy'],['validation','Validation'],['missing-data','Missing data'],['recovery','Recovery']]],
  ['testing','Testing workflows',[['unchanged','Non-mutation'],['deterministic','Determinism'],['round-trip','Serialization']]],
  // Advanced.
  ['numerics','Numerical kernels',[['black76-kernels','Black–76'],['spread-kernels','Spread models'],['exotic-kernels','Exotic kernels'],['simulation-kernels','Simulation'],['interpolation-kernels','Interpolation'],['root-kernels','Roots & bumps'],['measure-kernels','Risk adjustment']]],
  ['statistics','Statistics',[['descriptive','Descriptive'],['stationarity','Stationarity'],['mean-reversion','Mean reversion'],['normality','Normality']]],
  ['market-utils','Market utilities',[['transmission-utils','Transmission'],['weather-utils','Weather'],['outage-records','Outage records'],['reliability-kpis','Reliability KPIs']]],
  ['workflow-guide','Experimental: model selection',[['workflow-product','Product definition'],['workflow-criteria','Criteria'],['workflow-steps','Seven steps'],['workflow-result','Result & audit']]],
];
function renderGuideNav(){document.querySelector('#guide-nav').innerHTML=GUIDE_NAV.map(([route,label,children])=>`<details class="nav-group"><summary><a href="#/guide/${route}">${label}</a></summary><div>${children.map(([id,name])=>`<a href="#/guide/${route}" data-section="${id}">${name}</a>`).join('')}</div></details>`).join('')}

const metaDescriptionTag = document.querySelector('meta[name="description"]');
function setMeta(title, description) {
  document.title = title ? `${title} — QuantVolt` : 'QuantVolt documentation';
  if (metaDescriptionTag && description) metaDescriptionTag.setAttribute('content', description);
}

function pageFrame(title, description, body, breadcrumb='User guide') {
  return `<div class="breadcrumbs"><a href="#/overview">Docs</a><span>/</span><span>${esc(breadcrumb)}</span></div><header class="page-head"><h1>${esc(title)}</h1><p>${esc(description)}</p></header><article class="prose">${body}</article><footer class="page-footer"><span>QuantVolt v${API.version}</span><a href="https://github.com/nimabahrami/quantvolt">Edit or report an issue ↗</a></footer>`;
}

function renderGuide(key) {
  const guide = window.DOC_GUIDES[key] || window.DOC_GUIDES.overview;
  content.innerHTML = pageFrame(guide.title, guide.description, guide.body, key === 'overview' ? 'Overview' : 'User guide');
  if (key === 'overview') { document.title = guide.title; if (metaDescriptionTag) metaDescriptionTag.setAttribute('content', guide.description); }
  else setMeta(guide.title, guide.description);
  finishRender();
}

function kindBadge(kind) { return `<span class="kind ${kind}">${kind}</span>`; }
function inlineDoc(value){
  return esc(value)
    .replace(/``([^`]+)``/g,'<code>$1</code>')
    .replace(/:(?:class|func|meth|attr|mod|data|exc|const):`~?([^`]+)`/g,'<code>$1</code>')
    .replace(/`([^`]+)`/g,'<code>$1</code>');
}
function renderDoc(doc){
  if(!doc)return'';
  const sectionNames=new Set(['Args:','Arguments:','Parameters:','Keyword Args:','Other Parameters:','Attributes:','Returns:','Yields:','Raises:','Notes:','Examples:','Example:','Warnings:','See Also:','References:']);
  const chunks=[];
  let current={title:'',lines:[]};
  for(const line of doc.split('\n')){
    if(sectionNames.has(line.trim())){
      if(current.lines.some(item=>item.trim()))chunks.push(current);
      current={title:line.trim().slice(0,-1),lines:[]};
    }else current.lines.push(line);
  }
  if(current.lines.some(item=>item.trim()))chunks.push(current);
  return chunks.map(chunk=>{
    const text=chunk.lines.join('\n').trim();
    if(!text)return'';
    if(!chunk.title){
      const paragraphs=text.split(/\n\s*\n/).map(paragraph=>`<p>${inlineDoc(paragraph).replaceAll('\n','<br>')}</p>`).join('');
      return `<div class="api-description">${paragraphs}</div>`;
    }
    const rows=[];
    let active=null;
    for(const line of chunk.lines){
      const match=line.match(/^\s{4}([*\w][\w *.,-]*):\s*(.*)$/);
      if(match){active={name:match[1],text:match[2]};rows.push(active)}
      else if(active&&line.trim())active.text+=' '+line.trim();
    }
    const sectionId=slug(chunk.title);
    if(rows.length){
      const isError=chunk.title==='Raises';
      const rowClass=isError?'doc-row error-row':'doc-row variable-row';
      return `<h2 id="${sectionId}">${chunk.title}</h2><div class="doc-table ${isError?'error-table':'variable-table'}">${rows.map(row=>`<div class="${rowClass}"><code class="doc-name">${esc(row.name)}</code><p>${inlineDoc(row.text)}</p></div>`).join('')}</div>`;
    }
    const tone=chunk.title==='Warnings'?' warning-note':chunk.title==='Raises'?' error-note':'';
    return `<h2 id="${sectionId}">${chunk.title}</h2><div class="doc-section-note${tone}"><p>${inlineDoc(text).replaceAll('\n','<br>')}</p></div>`;
  }).join('');
}
function renderApiIndex() {
  const groups = API.modules.map((module) => `<a class="module-card" href="#/api/${module.name}"><div><code>${module.qualified}</code><span>${module.symbols.length} symbols</span></div><p>${esc(module.description)}</p><i>→</i></a>`).join('');
  const description = `Complete source-generated reference for ${API.symbolCount} public symbols across ${API.modules.length} modules.`;
  content.innerHTML = pageFrame('API reference', description, `<div class="reference-note">Generated from each package's <code>__all__</code>, signatures and docstrings. Run <code>python3 site/build_api.py</code> after API changes.</div><div class="module-grid">${groups}</div>`, 'API reference');
  setMeta('API reference', description);
  finishRender();
}

function renderModule(name) {
  const module = moduleByName(name);
  if (!module) return renderNotFound();
  const rows = module.symbols.map((symbol) => `<a class="symbol-row" href="#/api/${name}/${encodeURIComponent(symbol.name)}"><span>${kindBadge(symbol.kind)}<code>${esc(symbol.name)}</code></span><p>${esc(symbol.summary)}</p></a>`).join('');
  const byKind = ['class','function','constant'].map((kind) => ({kind, symbols: module.symbols.filter((symbol)=>symbol.kind===kind)})).filter((group)=>group.symbols.length);
  const summary = byKind.map((group)=>`<section><h2 id="${group.kind}s">${group.kind[0].toUpperCase()+group.kind.slice(1)}s <span>${group.symbols.length}</span></h2>${group.symbols.map((symbol)=>`<a class="api-chip" href="#/api/${name}/${encodeURIComponent(symbol.name)}"><code>${esc(symbol.name)}</code><span>→</span></a>`).join('')}</section>`).join('');
  const guide=MODULE_GUIDES[name]?`<div class="admonition note"><b>Looking for examples?</b><p>See the <a href="#/guide/${MODULE_GUIDES[name]}">${name} user guide</a> for complete workflows and result output.</p></div>`:'';
  content.innerHTML = pageFrame(module.qualified, module.description, `<div class="module-meta"><span>Module</span><code>from quantvolt import ${name}</code><button data-copy="from quantvolt import ${name}">Copy</button></div>${guide}${summary}<h2 id="all-symbols">All public symbols</h2><div class="symbol-table">${rows}</div>`, 'API reference');
  setMeta(module.qualified, module.description);
  finishRender();
}

function renderSymbol(moduleName, symbolName) {
  const symbol = symbolByName(moduleName, symbolName);
  if (!symbol) return renderNotFound();
  const fields = symbol.fields?.length ? `<h2 id="fields">Fields</h2><div class="doc-table">${symbol.fields.map((field)=>`<div class="doc-row variable-row"><code class="doc-name">${esc(field.name)}</code><p><span class="type-label">${esc(field.type)}</span>${field.default!==null?` · default <code>${esc(field.default)}</code>`:''}</p></div>`).join('')}</div>` : '';
  const members = symbol.members?.length ? `<h2 id="members">Members</h2><div class="doc-table">${symbol.members.map((member)=>`<div class="doc-row variable-row"><code class="doc-name">${esc(member.name)}</code><p><code class="member-value">${esc(member.value)}</code></p></div>`).join('')}</div>` : '';
  const methods = symbol.methods?.length ? `<h2 id="methods">Methods</h2><div class="method-list">${symbol.methods.map((method)=>`<div class="method-card"><code class="method-signature">${esc(method.signature)}</code><p>${inlineDoc(method.summary || 'Public method.')}</p></div>`).join('')}</div>` : '';
  const sourceUrl = `https://github.com/nimabahrami/quantvolt/blob/main/${symbol.source}#L${symbol.line}`;
  const doc = symbol.doc ? renderDoc(symbol.doc) : `<div class="api-description"><p>This public ${symbol.kind} is exported by <code>${moduleByName(moduleName)?.qualified}</code>. See the source for implementation details and validation behavior.</p></div>`;
  content.innerHTML = pageFrame(symbol.name, symbol.summary, `<div class="signature"><div>${kindBadge(symbol.kind)}<span>${esc(symbol.qualified)}</span><button data-copy="${esc(symbol.signature)}">Copy signature</button></div><pre><code>${esc(symbol.signature)}</code></pre></div><h2 id="description">Description</h2>${doc}${fields}${members}${methods}<h2 id="source">Source</h2><p>Defined in <a href="${sourceUrl}"><code>${esc(symbol.source)}:${symbol.line}</code> ↗</a></p><div class="prev-next"><a href="#/api/${moduleName}"><span>Module</span>← ${moduleByName(moduleName)?.qualified}</a><a href="#/api"><span>Reference</span>API index →</a></div>`, moduleByName(moduleName)?.qualified);
  setMeta(symbol.name, symbol.summary);
  finishRender();
}

function renderNotFound(){ const description='The requested documentation page does not exist.'; content.innerHTML=pageFrame('Page not found',description,`<div class="admonition error" role="alert"><b>Documentation error</b><p>The requested route does not match a generated guide or API symbol.</p><a href="#/overview">Return to the overview →</a></div>`,'404'); setMeta('Page not found', description); finishRender(); }
function finishRender(){ content.focus({preventScroll:true}); window.scrollTo(0,0); buildToc(); bindCopy(); updateActiveNav(); sidebar.classList.remove('open'); document.querySelector('#backdrop').classList.remove('show'); const pending=sessionStorage.getItem('qv-section');if(pending){sessionStorage.removeItem('qv-section');requestAnimationFrame(()=>scrollSection(pending))} }

function scrollSection(id){const target=document.getElementById(id);if(target)target.scrollIntoView({behavior:'smooth',block:'start'})}
function buildToc(){ const headings=[...content.querySelectorAll('.prose h2')]; toc.innerHTML=headings.map((heading)=>`<button type="button" data-section="${heading.id}">${heading.childNodes[0].textContent.trim()}</button>`).join('');toc.querySelectorAll('button').forEach((button)=>button.addEventListener('click',()=>scrollSection(button.dataset.section)));document.querySelector('#toc').classList.toggle('empty',!headings.length); }
function updateActiveNav(){ document.querySelectorAll('#side-nav a').forEach((link)=>link.classList.toggle('active',!link.dataset.section&&link.getAttribute('href')===location.hash));const active=document.querySelector('#side-nav a.active');if(active)active.closest('details')?.setAttribute('open',''); }
function route(){ const parts=(location.hash.slice(2)||'overview').split('/').map(decodeURIComponent); if(parts[0]==='overview') renderGuide('overview'); else if(parts[0]==='guide') renderGuide(parts[1]); else if(parts[0]==='api'&&!parts[1]) renderApiIndex(); else if(parts[0]==='api'&&parts[2]) renderSymbol(parts[1],parts[2]); else if(parts[0]==='api') renderModule(parts[1]); else renderNotFound(); }

function writeClipboard(text){ if(navigator.clipboard&&window.isSecureContext)return navigator.clipboard.writeText(text); const area=document.createElement('textarea');area.value=text;document.body.append(area);area.select();document.execCommand('copy');area.remove();return Promise.resolve(); }
function bindCopy(){ content.querySelectorAll('[data-copy]').forEach((button)=>button.addEventListener('click',()=>writeClipboard(button.dataset.copy).then(()=>{const old=button.textContent;button.textContent='Copied';toast.classList.add('show');setTimeout(()=>{button.textContent=old;toast.classList.remove('show')},1200)}))); }

const guideSearch = Object.entries(window.DOC_GUIDES).map(([key, guide])=>({name:guide.title, summary:guide.description, kind:'guide', href:key==='overview'?'#/overview':`#/guide/${key}`}));
const apiSearch = API.modules.flatMap((module)=>module.symbols.map((symbol)=>({...symbol,href:`#/api/${module.name}/${encodeURIComponent(symbol.name)}`})));
function search(query){const q=query.trim().toLowerCase();if(!q)return[];return [...guideSearch,...apiSearch].map((item)=>({...item,score:(item.name.toLowerCase()===q?100:0)+(item.name.toLowerCase().startsWith(q)?50:0)+(item.name.toLowerCase().includes(q)?25:0)+(item.summary.toLowerCase().includes(q)?5:0)})).filter((item)=>item.score).sort((a,b)=>b.score-a.score||a.name.localeCompare(b.name)).slice(0,12);}
function renderSearch(){const results=search(searchInput.value);state.selectedSearch=0;searchResults.innerHTML=results.length?results.map((item,index)=>`<a class="${index===0?'selected':''}" href="${item.href}"><span>${kindBadge(item.kind)}<b>${esc(item.name)}</b></span><small>${esc(item.summary)}</small></a>`).join(''):`<p class="search-hint">${searchInput.value?'No matching documentation.':'Type to search the complete QuantVolt API.'}</p>`;}
function setSearchScrollLock(locked){document.documentElement.classList.toggle('search-open',locked);document.body.classList.toggle('search-open',locked)}
function openSearch(){if(dialog.open)return;setSearchScrollLock(true);dialog.showModal();searchInput.value='';renderSearch();setTimeout(()=>searchInput.focus(),0)}
document.querySelector('#search-trigger').addEventListener('click',openSearch);searchInput.addEventListener('input',renderSearch);searchResults.addEventListener('click',()=>dialog.close());dialog.addEventListener('close',()=>setSearchScrollLock(false));
document.addEventListener('keydown',(event)=>{if(event.key==='/'&&!dialog.open&&!['INPUT','TEXTAREA'].includes(document.activeElement.tagName)){event.preventDefault();openSearch()} if(dialog.open&&['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();const links=[...searchResults.querySelectorAll('a')];if(!links.length)return;state.selectedSearch=(state.selectedSearch+(event.key==='ArrowDown'?1:-1)+links.length)%links.length;links.forEach((link,i)=>link.classList.toggle('selected',i===state.selectedSearch));links[state.selectedSearch].scrollIntoView({block:'nearest'})}if(dialog.open&&event.key==='Enter'){const selected=searchResults.querySelector('.selected');if(selected){event.preventDefault();location.hash=selected.getAttribute('href').slice(1);dialog.close()}}});
document.querySelector('#theme-button').addEventListener('click',()=>{const dark=document.documentElement.classList.toggle('dark');localStorage.setItem('qv-theme',dark?'dark':'light')});if(localStorage.getItem('qv-theme')==='dark'||(!localStorage.getItem('qv-theme')&&matchMedia('(prefers-color-scheme: dark)').matches))document.documentElement.classList.add('dark');
document.querySelector('#menu-button').addEventListener('click',()=>{sidebar.classList.add('open');document.querySelector('#backdrop').classList.add('show')});document.querySelector('#backdrop').addEventListener('click',()=>{sidebar.classList.remove('open');document.querySelector('#backdrop').classList.remove('show')});
document.querySelector('#side-nav').addEventListener('click',(event)=>{const link=event.target.closest('a[data-section]');if(!link)return;const destination=link.getAttribute('href');const section=link.dataset.section;if(location.hash===destination){event.preventDefault();scrollSection(section);sidebar.classList.remove('open');document.querySelector('#backdrop').classList.remove('show')}else{sessionStorage.setItem('qv-section',section)}});
content.addEventListener('click',(event)=>{const link=event.target.closest('a[data-section]');if(!link)return;event.preventDefault();scrollSection(link.dataset.section)});
renderGuideNav();renderModuleNav();window.addEventListener('hashchange',route);route();
