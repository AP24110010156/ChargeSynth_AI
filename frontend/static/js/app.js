'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const number = (value, digits = 0) => Number(value).toLocaleString('en-IN', {minimumFractionDigits: digits, maximumFractionDigits: digits});
  const settingsFields = {row_count:'rowCount',station_count:'stationCount',plugs_per_station:'plugsPerStation',scenario:'scenario',charger_type:'chargerType',start_date:'startDate',days:'days'};
  const planFields = {road_name:'roadName',reference_station:'referenceStation',existing_owner:'existingOwner',distance_km:'distanceKm',candidate_plugs:'candidatePlugs',additional_plugs:'additionalPlugs',growth_percent:'growthPercent',diversion_percent:'diversionPercent'};
  const textSettings = new Set(['scenario','charger_type','start_date']);
  const textPlans = new Set(['road_name','reference_station','existing_owner']);
  let seed = 42, run = null, proposal = null, assessment = null, page = 0, chartMode = 'arrivals', selectedHour = 17;
  let generationToken = 0, comparisonToken = 0, noticeTimer, navLock = 0, preferredReferenceStation = 'ST-01';
  const pageSize = 8;
  function node(tag, className, text) { const el = document.createElement(tag); if(className) el.className=className; if(text !== undefined) el.textContent=text; return el; }
  function message(id, text='') { $(id).textContent=text; $(id).hidden=!text; }
  function toast(text) { $('toast').textContent=text; $('toast').hidden=false; clearTimeout(noticeTimer); noticeTimer=setTimeout(()=>$('toast').hidden=true,3500); }
  async function api(path, body) {
    const controller = new AbortController();
    const timer = setTimeout(()=>controller.abort(),55000);
    try {
      const response = await fetch(path, body === undefined ? {signal:controller.signal} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal});
      const data = await response.json();
      if(!response.ok) throw new Error(data.error || 'The request could not be completed.');
      return data;
    } catch(error) {
      if(error.name==='AbortError') throw new Error('The request took too long. Please try again.');
      if(error instanceof TypeError) throw new Error('The studio is unreachable. Check that its terminal window is still running.');
      throw error;
    } finally { clearTimeout(timer); }
  }
  function settings() {
    const result={seed,demand_level:document.querySelector('input[name="demand"]:checked').value};
    for(const [key,id] of Object.entries(settingsFields)) result[key]=textSettings.has(key)?$(id).value:Number($(id).value);
    return result;
  }
  function planning() {
    const result={};
    for(const [key,id] of Object.entries(planFields)){
      const value=key==='reference_station'?($(id).value||preferredReferenceStation):$(id).value;
      result[key]=textPlans.has(key)?value:Number(value);
    }
    return result;
  }
  function fillSettings(s) {
    for(const [key,id] of Object.entries(settingsFields)) if(s[key]!==undefined) $(id).value=s[key];
    seed=s.seed;
    const demand=document.querySelector(`input[name="demand"][value="${s.demand_level}"]`);
    if(demand)demand.checked=true;
    hints();
  }
  function fillPlanning(p) {
    for(const [key,id] of Object.entries(planFields)){
      if(p[key]===undefined)continue;
      if(key==='reference_station')preferredReferenceStation=p[key];
      else $(id).value=p[key];
    }
    if(run)updateReferenceStations(preferredReferenceStation);
    ownerHint();
  }
  function hints() {
    const s=settings();
    $('capacityHint').textContent=`${number(s.station_count)} location${s.station_count===1?'':'s'} × ${number(s.plugs_per_station)} plugs = ${number(s.station_count*s.plugs_per_station)} vehicles charging at once.`;
    $('scenarioNote').hidden=!['mixed','holiday','festival'].includes(s.scenario);
    $('chargerAssumption').hidden=s.charger_type!=='mixed';
    $('arrivalHint').textContent={quiet:'Spread arrivals broadly across all 24 hours. The total number of visits stays the same.',normal:'Use varied morning, afternoon, evening or overnight peaks with background demand.',busy:'Concentrate demand around a seeded morning, afternoon, evening or overnight rush. Available plugs determine the queue.'}[s.demand_level];
    $('staleNote').hidden=!run || JSON.stringify(s)===JSON.stringify(currentSettingsInOrder());
  }
  function currentSettingsInOrder(){ const now=settings(); return Object.fromEntries(Object.keys(now).map(k=>[k,run.settings[k]])); }
  function stationMetrics(stationId){
    if(!run)return null;
    const item=(run.summary.stations||[]).find(station=>station.station_id===stationId)||{};
    const rows=run.rows.filter(row=>row.station_id===stationId);
    const waits=rows.map(row=>Number(row.queue_wait_minutes)||0);
    const sessions=item.sessions??rows.length;
    const waited=item.waiting_sessions??waits.filter(wait=>wait>0).length;
    const occupied=item.occupied_percent??item.occupancy_percent??0;
    return {
      station_id:stationId,
      sessions,
      plugs:item.plugs??run.settings.plugs_per_station,
      average_wait_minutes:item.average_wait_minutes??(waits.reduce((sum,value)=>sum+value,0)/Math.max(1,waits.length)),
      max_wait_minutes:item.max_wait_minutes??Math.max(0,...waits),
      waiting_percent:item.waiting_percent??(100*waited/Math.max(1,sessions)),
      occupied_percent:occupied,
      demand_share_percent:item.demand_share_percent??run.summary.station_demand_shares?.[stationId]??(100*sessions/Math.max(1,run.summary.sessions))
    };
  }
  function updateReferenceStations(preferred=preferredReferenceStation,notifyFallback=false){
    if(!run)return;
    const select=$('referenceStation');
    const ids=(run.summary.stations||[]).map(item=>item.station_id);
    if(!ids.length)ids.push(...new Set(run.rows.map(row=>row.station_id)));
    ids.sort();
    select.replaceChildren(...ids.map(id=>{const option=node('option','',id);option.value=id;return option;}));
    const selected=ids.includes(preferred)?preferred:ids[0];
    select.value=selected||'';
    preferredReferenceStation=select.value;
    if(notifyFallback&&preferred&&selected&&preferred!==selected)toast(`${preferred} is not in this sample. Reference changed to ${selected}.`);
    renderReferenceSummary();
  }
  function renderReferenceSummary(){
    if(!run)return;
    const metrics=stationMetrics($('referenceStation').value||preferredReferenceStation);
    if(!metrics)return;
    preferredReferenceStation=metrics.station_id;
    $('referenceVisits').textContent=number(metrics.sessions);
    $('referencePlugs').textContent=number(metrics.plugs);
    $('referenceAverageWait').textContent=`${number(metrics.average_wait_minutes,1)} min`;
    $('referenceMaximumWait').textContent=`${number(metrics.max_wait_minutes,1)} min`;
    $('referenceWaitingPercent').textContent=`${number(metrics.waiting_percent,1)}%`;
    $('referenceOccupancy').textContent=`${number(metrics.occupied_percent,1)}%`;
    $('additionalPlugsLabel').textContent=`Add plugs at ${metrics.station_id}`;
  }
  function ownerHint() {
    const competitor=$('existingOwner').value==='another_operator';
    $('additionalPlugs').disabled=competitor;
    const station=$('referenceStation').value||preferredReferenceStation;
    $('additionalPlugsLabel').textContent=`Add plugs at ${station}`;
    $('planningHint').textContent=competitor ? `${station} belongs to Another Operator and is a demand reference only. Expansion of that site is excluded.` : 'Growth and route choice are assumptions. Distance alone does not create demand.';
  }
  async function generate(newSample=false) {
    if(!$('generationForm').reportValidity()) return;
    if(newSample){const values=new Uint32Array(1);crypto.getRandomValues(values);seed=values[0]%2147483647;}
    const previousReference=$('referenceStation').value||preferredReferenceStation;
    const hadRun=Boolean(run);
    const token=++generationToken;
    comparisonToken++;
    $('generateButton').disabled=true; $('newSample').disabled=true; $('applyPlan').disabled=true;
    $('generateButton').querySelector('span').textContent='Generating…'; $('results').setAttribute('aria-busy','true');
    message('generationError');
    try{
      const data=await api('/api/generate',settings());
      if(token!==generationToken) return;
      run=data;page=0;assessment=null;
      $('searchRows').value=''; $('insightBox').hidden=true;
      updateReferenceStations(previousReference,hadRun);renderResults();renderTable();hints();ownerHint();
      await compare(false);
      if(newSample) toast('A new set of vehicles is ready.');
      return true;
    }catch(error){message('generationError',error.message);}
    finally{if(token===generationToken){$('generateButton').disabled=false;$('newSample').disabled=false;$('applyPlan').disabled=false;$('generateButton').querySelector('span').textContent='Generate sessions';$('results').setAttribute('aria-busy','false');}}
  }
  function renderResults() {
    const s=run.summary, config=run.settings;
    $('metricSessions').textContent=number(s.sessions);$('metricEnergy').textContent=number(s.total_energy_kwh);
    $('metricDuration').textContent=number(s.average_duration_minutes,1);$('metricWait').textContent=number(s.average_wait_minutes,1);
    $('navCount').textContent=number(s.sessions);$('tableCount').textContent=number(s.sessions);
    $('periodTag').textContent=`${s.eligible_days} day${s.eligible_days===1?'':'s'} · ${config.station_count} location${config.station_count===1?'':'s'}`;
    $('chartScope').textContent=`Totals across ${s.eligible_days} eligible day${s.eligible_days===1?'':'s'} · all ${config.station_count} location${config.station_count===1?'':'s'}`;
    $('capacitySummary').textContent=`${config.station_count} location${config.station_count===1?'':'s'} × ${config.plugs_per_station} plugs each`;
    $('capacityPlugs').textContent=number(s.total_plugs);$('waitingShare').textContent=`${number(s.waiting_percent,1)}%`;
    $('occupancyValue').textContent=`${number(s.occupied_percent,1)}%`;$('occupancyBar').style.width=`${s.occupied_percent}%`;
    $('maxWait').textContent=number(s.max_wait_minutes,1);
    $('queueInterpretation').textContent=s.average_wait_minutes>30?'Arrivals exceed available capacity at busy times. Compare adding plugs or another site.':s.waiting_sessions>0?'Some arrivals overlap. More plugs may reduce the queue without changing vehicle energy needs.':'Every arriving vehicle found a free plug. Extra capacity may also show zero waiting time.';
    $('simulationNote').textContent=`Synthetic scenarios, not observed traffic. ${s.sessions_finishing_after_window?`${number(s.sessions_finishing_after_window)} visits finish after the selected arrival period; their full charging sessions remain in the CSV. `:''}Mixed, holiday and festival labels are hypothetical rather than a verified public calendar.`;
    $('stationRows').replaceChildren();
    for(const item of s.stations){
      const metrics=stationMetrics(item.station_id);
      const row=node('div','station-row');
      const label=node('div');
      label.append(node('strong','',metrics.station_id),node('small','',`${number(metrics.sessions)} visits · ${number(metrics.plugs)} plugs`),node('small','',`${number(metrics.demand_share_percent,1)}% demand share`));
      const bar=node('div','meter');const fill=node('i');fill.style.width=`${Math.min(100,metrics.occupied_percent)}%`;bar.append(fill);bar.title=`${number(metrics.occupied_percent,1)}% occupancy in selected period`;
      const stats=node('div','station-stats');
      stats.append(node('span','',`Avg ${number(metrics.average_wait_minutes,1)} min`),node('span','',`Max ${number(metrics.max_wait_minutes,1)} min`),node('span','',`${number(metrics.waiting_percent,1)}% waited`),node('span','',`${number(metrics.occupied_percent,1)}% occupied`));
      row.append(label,bar,stats);$('stationRows').append(row);
    }
    renderReferenceSummary();
    selectedHour=s.peak_arrival_hour;renderChart();$('downloadButton').disabled=false;
  }
  function niceStep(value) {
    if(value<=4) return 1;
    const raw=value/4,power=10**Math.floor(Math.log10(raw));
    return [1,2,2.5,5,10].find(x=>x*power>=raw)*power;
  }
  function renderChart() {
    if(!run)return;
    const values=chartMode==='arrivals'?run.summary.arrivals_by_hour:run.summary.energy_by_arrival_hour;
    const step=niceStep(Math.max(...values)),top=step*4;
    $('chartYLabel').textContent=chartMode==='arrivals'?'VEHICLE ARRIVALS (COUNT)':'ENERGY REQUESTED (kWh)';
    $('hourBars').replaceChildren();$('yTicks').replaceChildren();$('gridLines').replaceChildren();
    for(let i=0;i<=4;i++){const tick=node('span','',number(step*i));tick.style.bottom=`${i*25}%`;$('yTicks').append(tick);const line=node('i');line.style.bottom=`${i*25}%`;$('gridLines').append(line);}
    values.forEach((value,hour)=>{
      const button=node('button','hour-bar');button.type='button';button.dataset.hour=hour;
      button.style.setProperty('--height',`${value/top*100}%`);
      button.setAttribute('aria-label',hourDescription(hour));button.title=hourDescription(hour);
      button.setAttribute('aria-pressed',String(hour===selectedHour));button.tabIndex=hour===selectedHour?0:-1;
      button.classList.toggle('selected',hour===selectedHour);
      button.append(node('span','bar'),node('span','tick',hour%3===0?String(hour).padStart(2,'0'):''));
      button.addEventListener('pointerenter',()=>selectHour(hour));button.addEventListener('focus',()=>selectHour(hour));button.addEventListener('click',()=>selectHour(hour));
      button.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();let next=event.key==='Home'?0:event.key==='End'?23:(hour+(event.key==='ArrowRight'?1:23))%24;$('hourBars').children[next].focus();}});
      $('hourBars').append(button);
    });selectHour(selectedHour);
  }
  function hourDescription(hour){const s=run.summary;return `${String(hour).padStart(2,'0')}:00–${String(hour).padStart(2,'0')}:59 IST: ${s.arrivals_by_hour[hour]} visits, ${s.energy_by_arrival_hour[hour]} kWh requested, ${s.wait_by_arrival_hour[hour]} minutes average queue.`;}
  function selectHour(hour){
    if(!run)return;selectedHour=hour;const s=run.summary;
    $('selectedHour').textContent=`${String(hour).padStart(2,'0')}:00–${String(hour).padStart(2,'0')}:59 IST`;
    $('selectedCount').textContent=`${number(s.arrivals_by_hour[hour])} visits`;
    $('selectedEnergy').textContent=`${number(s.energy_by_arrival_hour[hour],1)} kWh`;
    $('selectedWait').textContent=`${number(s.wait_by_arrival_hour[hour],1)} min avg. queue`;
    for(const bar of $('hourBars').children){const active=Number(bar.dataset.hour)===hour;bar.classList.toggle('selected',active);bar.setAttribute('aria-pressed',String(active));bar.tabIndex=active?0:-1;}
  }
  function dateLabel(value, full=false){return new Date(value).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',day:'2-digit',month:'short',...(full?{year:'numeric',second:'2-digit'}:{}),hour:'2-digit',minute:'2-digit',hour12:false});}
  function filteredRows(){const q=$('searchRows').value.trim().toLowerCase();return !q?run.rows:run.rows.filter(r=>[r.session_id,r.station_id,r.plug_id,r.charger_type,r.day_type,r.vehicle_type].some(v=>String(v).toLowerCase().includes(q)));}
  function renderTable(){
    if(!run)return;const rows=filteredRows(),pages=Math.max(1,Math.ceil(rows.length/pageSize));page=Math.min(page,pages-1);$('sessionRows').replaceChildren();
    for(const row of rows.slice(page*pageSize,(page+1)*pageSize)){
      const tr=node('tr');
      const station=node('td','',row.station_id);station.append(node('small','',row.plug_id));
      const soc=node('td','',`${number(row.soc_in)} → ${number(row.soc_out)}%`);
      const details=node('td');const open=node('button','text-button','View ↗');open.setAttribute('aria-label',`View session ${row.session_id}`);open.addEventListener('click',()=>showRow(row));details.append(open);
      tr.append(node('td','',row.session_id),station,node('td','',dateLabel(row.arrival_time)),node('td','',`${number(row.queue_wait_minutes,1)} min`),node('td','',`${number(row.duration_minutes,1)} min`),node('td','',`${number(row.kwh_consumed,1)} kWh`),soc,details);$('sessionRows').append(tr);
    }
    if(!rows.length){const tr=node('tr');const td=node('td','','No matching sessions. Try a station such as ST-01.');td.colSpan=8;tr.append(td);$('sessionRows').append(tr);}
    $('pageLabel').textContent=rows.length?`${page*pageSize+1}–${Math.min((page+1)*pageSize,rows.length)} of ${number(rows.length)} visits`:'0 matching visits';
    $('pageNumber').textContent=`${page+1} / ${pages}`;$('prevPage').disabled=page===0;$('nextPage').disabled=page>=pages-1;
  }
  const labels={session_id:'Session ID',station_id:'Station location',plug_id:'Charging plug',day_type:'Day scenario',day_of_week:'Day of the week',calendar_basis:'Calendar basis',arrival_time:'Arrival at station',plug_in_time:'Plug connected',start_time:'Charging begins',end_time:'Charging ends',plug_out_time:'Plug disconnected',exit_time:'Vehicle leaves',duration_minutes:'Charging time (minutes)',connected_minutes:'Plug occupied (minutes)',queue_wait_minutes:'Queue wait (minutes)',kwh_consumed:'Grid energy (kWh)',vehicle_type:'Vehicle type',charger_type:'Charger type',charger_power_kw:'Charger rating (kW)',average_power_kw:'Average charging power (kW)',battery_capacity_kwh:'Battery size (kWh)',soc_in:'Battery on arrival (%)',soc_out:'Battery after charging (%)',charging_efficiency:'Grid-to-battery efficiency',source:'Data origin'};
  function showRow(row){$('rowTitle').textContent=row.session_id;$('recordDetails').replaceChildren();for(const[key,label]of Object.entries(labels)){const item=node('div');let value=row[key];if(key.endsWith('_time'))value=dateLabel(value,true)+' IST';if(key==='charging_efficiency')value=`${number(value*100)}%`;if(key==='source')value='Synthetic demand + charging capacity simulation';if(key==='calendar_basis')value=value==='hypothetical_special_day'?'Hypothetical special day':'Calendar weekday / weekend';item.append(node('dt','',label),node('dd','',String(value)));$('recordDetails').append(item);}$('rowDialog').showModal();}
  async function compare(showToast=true){
    if(!run || !$('planningForm').reportValidity())return;
    const token=++comparisonToken,id=run.run_id,options=planning();
    $('compareButton').disabled=true;$('explainButton').disabled=true;$('comparisonResults').setAttribute('aria-busy','true');message('planningError');
    try{const data=await api('/api/assess',{run_id:id,planning:options});if(token!==comparisonToken || run.run_id!==id)return;if(JSON.stringify(options)!==JSON.stringify(planning())){$('comparisonBasis').textContent='Planning assumptions changed. Compare options to update the figures below.';return;}assessment=data;renderAssessment();$('insightBox').hidden=true;if(showToast)toast('Capacity options compared using the same future arrivals.');}
    catch(error){if(token===comparisonToken){message('planningError',error.message);assessment=null;$('comparisonCards').replaceChildren();$('recommendationTitle').textContent='Comparison not available.';$('recommendationText').textContent='Resolve the message above, then compare again.';$('comparisonBasis').textContent='No current comparison.';}}
    finally{if(token===comparisonToken){$('compareButton').disabled=false;$('explainButton').disabled=!assessment;$('comparisonResults').setAttribute('aria-busy','false');}}
  }
  function renderAssessment(){
    const a=assessment,p=a.assumptions;
    const reference=a.reference_station||p.reference_station||preferredReferenceStation;
    const current=stationMetrics(reference);
    const b=a.baseline.average_wait_minutes;
    $('routeSource').textContent=`${p.existing_owner==='our_network'?'Our Network':'Another Operator'} · ${reference}`;
    $('routeSourceInfo').textContent=`${number(current?.plugs??run.settings.plugs_per_station)} plugs · ${number(a.baseline_source_sessions)} reference visits`;
    $('routeCandidateInfo').textContent=`${p.candidate_plugs} plugs · ${number(a.candidate_sessions_per_day,1)} visits / day`;
    $('routeDistance').textContent=`${p.distance_km} km proposed separation`;
    $('comparisonBasis').textContent=`${p.road_name} · selected reference ${reference} has ${a.baseline_source_sessions} visits. ${p.growth_percent}% assumed growth gives ${a.future_sessions} future visits over ${a.eligible_days} eligible day${a.eligible_days===1?'':'s'}; ${a.candidate_sessions} are explicitly assigned to the candidate. All options reuse that exact future vehicle cohort and its arrival times. Distance alone does not change demand.`;
    $('comparisonCards').replaceChildren();
    const specs=[
      ['Keep current capacity',`${number(current?.plugs??run.settings.plugs_per_station)} plugs at ${reference}`,a.baseline,'Reference capacity for the identical future cohort'],
      [`Expand ${reference}`,`${p.additional_plugs} additional plugs at the selected station`,a.expanded,a.expanded?`${number(Math.max(0,b-a.expanded.average_wait_minutes),1)} min less average waiting than current capacity`:`Unavailable: ${reference} belongs to Another Operator`],
      ['Open candidate NEW-01',`${p.candidate_plugs} plugs · ${p.distance_km} km user-provided distance`,a.new_site,`${a.candidate_sessions} visits choose the candidate by assumption`]
    ];
    specs.forEach(([title,sub,data,foot],index)=>{
      const card=node('article','comparison-card'+(!data?' unavailable':''));
      const val=node('div','comparison-value',data?number(data.average_wait_minutes,1):'Not available');
      if(data)val.append(node('small','',' min'));
      card.append(node('h3','',title),node('p','',sub),val,node('div','comparison-label',data?'Average wait across all future visits':"Another operator's station cannot be expanded"));
      if(data){
        const metrics=node('dl','comparison-metrics');
        const items=[['Maximum wait',`${number(data.max_wait_minutes??0,1)} min`],['Visits waited',`${number(data.waiting_percent??0,1)}%`],['Occupancy',`${number(data.occupied_percent??0,1)}%`],['Future visits',number(data.sessions??a.future_sessions)]];
        for(const [label,value] of items){const item=node('div');item.append(node('dt','',label),node('dd','',value));metrics.append(item);}
        card.append(metrics);
      }
      const footer=node('div','comparison-foot',foot);
      if(index===2&&a.candidate){
        footer.append(node('span','candidate-queue',`Candidate-site queue: ${number(a.candidate.average_wait_minutes??0,1)} min average · ${number(a.candidate.max_wait_minutes??0,1)} min maximum · ${number(a.candidate.waiting_percent??0,1)}% waited · ${number(a.candidate.occupied_percent??0,1)}% occupancy.`));
      }
      card.append(footer);$('comparisonCards').append(card);
    });
    $('recommendationTitle').textContent=a.headline;
    $('recommendationText').textContent=String(a.explanation).includes(reference)?a.explanation:`For ${reference}, ${a.explanation}`;
    $('assumptionNotes').replaceChildren(...(a.notes||[]).map(text=>node('li','',text)));
  }
  function setActive(id){for(const link of document.querySelectorAll('.nav-link')){const active=link.dataset.section===id;link.classList.toggle('active',active);if(active)link.setAttribute('aria-current','location');else link.removeAttribute('aria-current');} $('currentSection').textContent={workspace:'Session studio',planning:'Station planning',dataset:'Session data'}[id];}
  document.querySelectorAll('a[href^="#"]').forEach(link=>link.addEventListener('click',()=>{const id=link.getAttribute('href').slice(1);if(['workspace','planning','dataset'].includes(id)){navLock=Date.now()+900;setActive(id);}}));
  let scrollQueued=false;window.addEventListener('scroll',()=>{if(scrollQueued)return;scrollQueued=true;requestAnimationFrame(()=>{scrollQueued=false;if(Date.now()<navLock)return;let id='workspace';for(const section of ['workspace','planning','dataset'])if($(section).getBoundingClientRect().top<155)id=section;if(window.innerHeight+window.scrollY>=document.documentElement.scrollHeight-20)id='dataset';setActive(id);});},{passive:true});
  $('generationForm').addEventListener('submit',e=>{e.preventDefault();generate();});$('generationForm').addEventListener('input',hints);$('newSample').addEventListener('click',()=>generate(true));
  $('planningForm').addEventListener('submit',e=>{e.preventDefault();compare();});$('planningForm').addEventListener('input',()=>{ownerHint();$('insightBox').hidden=true;if(assessment)$('comparisonBasis').textContent='Planning assumptions changed. Compare options to update the figures below.';});
  $('referenceStation').addEventListener('change',()=>{preferredReferenceStation=$('referenceStation').value;renderReferenceSummary();ownerHint();if(run)compare(false);});
  $('showArrivals').addEventListener('click',()=>setChart('arrivals'));$('showEnergy').addEventListener('click',()=>setChart('energy'));
  function setChart(mode){chartMode=mode;for(const [id,m] of [['showArrivals','arrivals'],['showEnergy','energy']]){$(id).classList.toggle('selected',mode===m);$(id).setAttribute('aria-pressed',String(mode===m));}renderChart();}
  $('searchRows').addEventListener('input',()=>{page=0;renderTable();});$('prevPage').addEventListener('click',()=>{page--;renderTable();});$('nextPage').addEventListener('click',()=>{page++;renderTable();});
  $('downloadButton').addEventListener('click',()=>{if(run)window.location.assign(run.download_url);});
  $('closeRow').addEventListener('click',()=>$('rowDialog').close());$('rowDialog').addEventListener('click',e=>{if(e.target===$('rowDialog')){const r=$('rowDialog').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('rowDialog').close();}});
  document.querySelectorAll('[data-prompt]').forEach(button=>button.addEventListener('click',()=>{$('scenarioPrompt').value=button.dataset.prompt;$('scenarioPrompt').focus();}));
  $('planButton').addEventListener('click',async()=>{
    if(!$('generationForm').reportValidity()||!$('planningForm').reportValidity())return;
    $('planButton').disabled=true;message('planError');$('planResult').hidden=true;proposal=null;
    try{proposal=await api('/api/plan',{prompt:$('scenarioPrompt').value,settings:settings(),planning:planning()});$('planExplanation').textContent=proposal.explanation;$('planNotice').textContent=proposal.notice;$('planResult').hidden=false;}
    catch(error){message('planError',error.message);}finally{$('planButton').disabled=false;}
  });
  $('applyPlan').addEventListener('click',async()=>{if(!proposal)return;fillSettings(proposal.settings);fillPlanning(proposal.planning);if(await generate())toast('Scenario applied. Review the station comparison below.');});
  $('explainButton').addEventListener('click',async()=>{
    if(!run||!$('planningForm').reportValidity())return;
    const id=run.run_id,assumptions=planning();$('explainButton').disabled=true;$('insightBox').hidden=false;$('insightText').textContent='Preparing your station assessment…';$('insightNotice').textContent='';
    try{const data=await api('/api/explain',{run_id:id,planning:assumptions});if(run.run_id!==id || JSON.stringify(assumptions)!==JSON.stringify(planning())){$('insightBox').hidden=true;return;}assessment=data.assessment;renderAssessment();$('insightText').textContent=data.explanation;$('insightNotice').textContent=data.notice;}
    catch(error){$('insightText').textContent=error.message;}
    finally{$('explainButton').disabled=!run;}
  });
  $('closeInsight').addEventListener('click',()=>$('insightBox').hidden=true);
  (async()=>{try{const status=await api('/api/status');fillSettings(status.default_settings);fillPlanning(status.default_planning);await generate();}catch(error){message('generationError',error.message);$('periodTag').textContent='Waiting for studio';}})();
})();
