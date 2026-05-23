// Working single-file tools that match the Oneline design system. Each builder
// returns complete HTML. The inner scripts use no backticks and no template
// placeholders, so the only interpolation is the variant marker comment.

import type { Accent, ToolCategory, UxEmphasis } from "../types";
import { htmlShell } from "./shell";

function marker(emphasis: UxEmphasis): string {
  return "<!-- oneline candidate emphasis: " + emphasis + " -->\n";
}

// ---- Interval timer (red accent, workout urgency) ----
export function timerTool(accent: string, emphasis: UxEmphasis = "polish"): string {
  const body =
    marker(emphasis) +
    `<main class="ol-app">
  <div class="ol-top">
    <h1 class="ol-title">Interval timer</h1>
    <p class="ol-label" id="phaseLabel">Ready</p>
  </div>
  <div class="ol-mid">
    <div class="ol-chips" id="rounds"></div>
    <div class="ol-hero accent" id="clock">00:30</div>
  </div>
  <div class="ol-dock">
    <button class="ol-btn ol-btn-primary" id="startBtn">Start workout</button>
    <button class="ol-btn ol-btn-secondary" id="resetBtn">Reset</button>
  </div>
</main>`;
  const script = `
var rounds=4, work=30, rest=15;
var idx=0, inWork=true, remaining=work, running=false, timer=null;
var clock=document.getElementById('clock');
var phaseLabel=document.getElementById('phaseLabel');
var startBtn=document.getElementById('startBtn');
var resetBtn=document.getElementById('resetBtn');
var roundsEl=document.getElementById('rounds');
function two(n){return (n<10?'0':'')+n;}
function fmt(s){return two(Math.floor(s/60))+':'+two(s%60);}
function renderRounds(){var h='';for(var i=0;i<rounds;i++){h+='<span class="ol-chip'+(i===idx?' active':'')+'">R'+(i+1)+'</span>';}roundsEl.innerHTML=h;}
function render(){clock.textContent=fmt(remaining);phaseLabel.textContent=running?(inWork?'Work':'Rest'):'Ready';startBtn.textContent=running?'Pause':'Start workout';renderRounds();}
function tick(){remaining-=1;if(remaining<0){if(inWork){inWork=false;remaining=rest;}else{inWork=true;idx+=1;remaining=work;if(idx>=rounds){finish();return;}}}render();}
function finish(){running=false;clearInterval(timer);timer=null;clock.textContent='Done';phaseLabel.textContent='All rounds complete';startBtn.textContent='Start workout';idx=0;}
startBtn.addEventListener('click',function(){if(running){running=false;clearInterval(timer);timer=null;render();return;}if(clock.textContent==='Done'){idx=0;inWork=true;remaining=work;}running=true;timer=setInterval(tick,1000);render();});
resetBtn.addEventListener('click',function(){running=false;if(timer)clearInterval(timer);timer=null;idx=0;inWork=true;remaining=work;render();});
render();`;
  return htmlShell({ title: "Interval timer", accent, bodyHtml: body, script });
}

// ---- Flashcards (violet accent, learning) ----
export function flashcardsTool(accent: string, emphasis: UxEmphasis = "polish"): string {
  const body =
    marker(emphasis) +
    `<main class="ol-app">
  <div class="ol-top">
    <h1 class="ol-title">Flashcards</h1>
    <p class="ol-label" id="counter">Card 1 of 5</p>
  </div>
  <div class="ol-mid">
    <div class="ol-card ol-fade" id="card" style="min-height:180px;display:flex;align-items:center;justify-content:center;text-align:center;cursor:pointer">
      <div>
        <div class="ol-hero" id="face" style="font-size:34px">term</div>
        <p class="ol-label" id="hint" style="margin-top:8px">Tap to flip</p>
      </div>
    </div>
    <div class="ol-progress"><i id="bar"></i></div>
  </div>
  <div class="ol-dock">
    <button class="ol-btn ol-btn-primary" id="nextBtn">Next card</button>
  </div>
</main>`;
  const script = `
var deck=[{t:'annyeong',d:'hello (casual)'},{t:'gamsahamnida',d:'thank you'},{t:'mul',d:'water'},{t:'sagwa',d:'apple'},{t:'hakgyo',d:'school'}];
var i=0, showBack=false;
var face=document.getElementById('face');
var hint=document.getElementById('hint');
var counter=document.getElementById('counter');
var card=document.getElementById('card');
var bar=document.getElementById('bar');
var nextBtn=document.getElementById('nextBtn');
function render(){card.style.opacity='0';setTimeout(function(){face.textContent=showBack?deck[i].d:deck[i].t;hint.textContent=showBack?'Tap to flip back':'Tap to flip';counter.textContent='Card '+(i+1)+' of '+deck.length;bar.style.width=(((i+1)/deck.length)*100)+'%';card.style.opacity='1';},120);}
card.addEventListener('click',function(){showBack=!showBack;render();});
nextBtn.addEventListener('click',function(){i=(i+1)%deck.length;showBack=false;render();});
render();`;
  return htmlShell({ title: "Flashcards", accent, bodyHtml: body, script });
}

// ---- Decision picker (teal accent, calm utility) ----
export function decisionTool(accent: string, emphasis: UxEmphasis = "polish"): string {
  const body =
    marker(emphasis) +
    `<main class="ol-app">
  <div class="ol-top">
    <h1 class="ol-title">Decide for me</h1>
    <p class="ol-label">Add options, then pick one</p>
  </div>
  <div class="ol-mid">
    <div class="ol-hero accent ol-fade" id="result" style="font-size:36px;min-height:44px">Ready</div>
    <div class="ol-list" id="list" style="max-height:160px"></div>
  </div>
  <div class="ol-dock">
    <input class="ol-input" id="opt" placeholder="Add an option" />
    <button class="ol-btn ol-btn-primary" id="pickBtn">Pick one</button>
  </div>
</main>`;
  const script = `
var options=['Tacos','Ramen','Salad','Pizza'];
var list=document.getElementById('list');
var result=document.getElementById('result');
var opt=document.getElementById('opt');
var pickBtn=document.getElementById('pickBtn');
function render(){var h='';for(var i=0;i<options.length;i++){h+='<div class="ol-row">'+options[i]+'</div>';}list.innerHTML=h;}
opt.addEventListener('keydown',function(e){if(e.key==='Enter'&&opt.value.trim()){options.push(opt.value.trim());opt.value='';render();}});
pickBtn.addEventListener('click',function(){if(!options.length)return;result.style.opacity='0';setTimeout(function(){result.textContent=options[Math.floor(Math.random()*options.length)];result.style.opacity='1';},150);});
render();`;
  return htmlShell({ title: "Decide for me", accent, bodyHtml: body, script });
}

// ---- Counter / tracker (green accent, progress) ----
export function counterTool(accent: string, emphasis: UxEmphasis = "polish"): string {
  const body =
    marker(emphasis) +
    `<main class="ol-app">
  <div class="ol-top">
    <h1 class="ol-title">Counter</h1>
    <p class="ol-label" id="sub">Tap to count</p>
  </div>
  <div class="ol-mid">
    <div class="ol-hero accent" id="count">0</div>
    <div class="ol-list" id="log" style="max-height:140px"></div>
  </div>
  <div class="ol-dock">
    <button class="ol-btn ol-btn-primary" id="addBtn">Add one</button>
    <button class="ol-btn ol-btn-secondary" id="resetBtn">Reset</button>
  </div>
</main>`;
  const script = `
var count=0, hist=[];
var countEl=document.getElementById('count');
var log=document.getElementById('log');
var addBtn=document.getElementById('addBtn');
var resetBtn=document.getElementById('resetBtn');
function two(n){return (n<10?'0':'')+n;}
function now(){var d=new Date();return two(d.getHours())+':'+two(d.getMinutes())+':'+two(d.getSeconds());}
function render(){countEl.textContent=String(count);var h='';for(var i=hist.length-1;i>=0;i--){h+='<div class="ol-row">#'+hist[i].n+' at '+hist[i].t+'</div>';}log.innerHTML=h;}
addBtn.addEventListener('click',function(){count+=1;hist.push({n:count,t:now()});render();});
resetBtn.addEventListener('click',function(){count=0;hist=[];render();});
render();`;
  return htmlShell({ title: "Counter", accent, bodyHtml: body, script });
}

// ---- Checklist (blue accent, neutral) ----
export function checklistTool(accent: string, emphasis: UxEmphasis = "polish"): string {
  const body =
    marker(emphasis) +
    `<main class="ol-app">
  <div class="ol-top">
    <h1 class="ol-title">Checklist</h1>
    <p class="ol-label" id="sub">0 of 0 done</p>
  </div>
  <div class="ol-mid" style="justify-content:flex-start;align-items:stretch">
    <div class="ol-list" id="list" style="max-height:100%;width:100%"></div>
  </div>
  <div class="ol-dock">
    <input class="ol-input" id="item" placeholder="Add an item" />
    <button class="ol-btn ol-btn-primary" id="addBtn">Add item</button>
  </div>
</main>`;
  const script = `
var items=[{t:'Passport',done:false},{t:'Charger',done:false},{t:'Tickets',done:false}];
var list=document.getElementById('list');
var sub=document.getElementById('sub');
var item=document.getElementById('item');
var addBtn=document.getElementById('addBtn');
function render(){var done=0,h='';for(var i=0;i<items.length;i++){if(items[i].done)done++;h+='<div class="ol-row'+(items[i].done?' done':'')+'" data-i="'+i+'"><span class="ol-checkbox'+(items[i].done?' on':'')+'"></span><span>'+items[i].t+'</span></div>';}list.innerHTML=h;sub.textContent=done+' of '+items.length+' done';var rows=list.querySelectorAll('.ol-row');for(var j=0;j<rows.length;j++){rows[j].addEventListener('click',function(){var k=parseInt(this.getAttribute('data-i'),10);items[k].done=!items[k].done;render();});}}
function add(){if(item.value.trim()){items.push({t:item.value.trim(),done:false});item.value='';render();}}
item.addEventListener('keydown',function(e){if(e.key==='Enter')add();});
addBtn.addEventListener('click',add);
render();`;
  return htmlShell({ title: "Checklist", accent, bodyHtml: body, script });
}

// ---- Category routing ----
export interface CategorySpec {
  category: ToolCategory;
  accent: Accent;
  build: (accent: string, emphasis: UxEmphasis) => string;
}

const TIMER: CategorySpec = { category: "timer", accent: "#F85149", build: timerTool };
const FLASH: CategorySpec = { category: "flashcards", accent: "#A371F7", build: flashcardsTool };
const DECIDE: CategorySpec = { category: "decision_tool", accent: "#2DD4BF", build: decisionTool };
const TRACK: CategorySpec = { category: "tracker", accent: "#3FB950", build: counterTool };
const CHECK: CategorySpec = { category: "checklist", accent: "#5B8DEF", build: checklistTool };

// Stems, matched as substrings, so plurals and inflections route correctly
// (flashcards, words, learning, groceries).
const RULES: Array<{ re: RegExp; spec: CategorySpec }> = [
  { re: /(timer|interval|workout|hiit|pomodoro|tabata|stretch|plank|countdown)/i, spec: TIMER },
  { re: /(flashcard|flash card|vocab|word|study|learn|memor|korean|spanish|french|japanese|quiz)/i, spec: FLASH },
  { re: /(decid|decision|choose|choice|random|pick|wheel|spinner|what should)/i, spec: DECIDE },
  { re: /(count|track|tally|habit|water|pushup|push up|\brep\b|steps|drink|streak)/i, spec: TRACK },
  { re: /(checklist|check list|todo|to do|packing|pack|grocery|groceries|task|shopping)/i, spec: CHECK },
];

// Direct category to spec mapping. Used when the category is already decided so
// we never re-run the keyword rules (which can miss a category name).
const CATEGORY_SPEC: Record<ToolCategory, CategorySpec> = {
  timer: TIMER,
  flashcards: FLASH,
  quiz: FLASH,
  decision_tool: DECIDE,
  randomizer: DECIDE,
  single_user_game: DECIDE,
  tracker: TRACK,
  log: TRACK,
  calculator: TRACK,
  converter: TRACK,
  display_only: TRACK,
  utility: TRACK,
  checklist: CHECK,
  planner: CHECK,
};

export function specForCategory(cat: ToolCategory): CategorySpec {
  return CATEGORY_SPEC[cat] || TRACK;
}

// Out-of-scope intake. The planner rejects these and suggests an in-scope alternative.
const OUT_OF_SCOPE = /\b(login|log in|sign up|signup|account|auth|password|multiplayer|multi user|multi-user|payment|stripe|checkout|database|backend|server|social network|marketplace|invite friends|chat with|message friends|upload to cloud|sync across)\b/i;

export function isOutOfScope(need: string): boolean {
  return OUT_OF_SCOPE.test(need || "");
}

export function classify(need: string): CategorySpec {
  for (const rule of RULES) {
    if (rule.re.test(need || "")) return rule.spec;
  }
  return TRACK;
}

// The pre-built fallback tool used when a live build is unavailable. An interval
// timer, one of the tools held ready for the demo.
export function fallbackTool(): { html: string; category: ToolCategory; accent: Accent } {
  return { html: timerTool("#F85149", "polish"), category: "timer", accent: "#F85149" };
}
