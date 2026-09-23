import { Check, ChevronDown, Search } from "lucide-react";
import {useEffect,useId,useRef,useState,type ReactNode,type KeyboardEvent} from "react";
import {OverlayPortal,useOverlayRegistration,useOverlayZIndex} from "./overlay/OverlaySystem";
import {useAnchoredPosition} from "./overlay/useAnchoredPosition";
import "./Select.css";
export type SelectOption={value:string;label?:string;detail?:string;group?:string;icon?:ReactNode};
export type SelectProps={value:string;options:SelectOption[];onChange:(value:string)=>void;ariaLabel?:string;disabled?:boolean;searchable?:boolean;searchPlaceholder?:string;tooltip?:string;rawValue?:string;testId?:string};
export function Select({value,options,onChange,ariaLabel="选择选项",disabled,searchable,searchPlaceholder="搜索",tooltip,rawValue,testId}:SelectProps){
 const [open,setOpen]=useState(false),[query,setQuery]=useState("");
 const anchor=useRef<HTMLButtonElement>(null);
 const {surfaceRef,style,placement}=useAnchoredPosition(anchor,open,"down",340,true);
 const layer=useOverlayZIndex(20), id=useId();
 const selected=options.find(x=>x.value===value);
 const filtered=options.filter(x=>`${x.label??x.value} ${x.detail??""} ${x.group??""}`.toLowerCase().includes(query.toLowerCase()));
 const close=()=>{setOpen(false);setQuery("");};
 useOverlayRegistration(open,close);
 useEffect(()=>{if(!open)return;const listener=(e:PointerEvent)=>{if(!anchor.current?.contains(e.target as Node)&&!surfaceRef.current?.contains(e.target as Node))close();};document.addEventListener("pointerdown",listener,true);return()=>document.removeEventListener("pointerdown",listener,true);},[open,surfaceRef]);
 useEffect(()=>{if(open&&!searchable)surfaceRef.current?.querySelector<HTMLButtonElement>('[aria-selected="true"], [role="option"]')?.focus();},[open,searchable,surfaceRef]);
 const keyboard=(e:KeyboardEvent)=>{
  if(e.defaultPrevented)return;
  if(open&&e.key==="Escape"){e.preventDefault();e.stopPropagation();close();anchor.current?.focus();return;}
  if(e.key==="Tab"){close();anchor.current?.focus();return;}
  if(!["ArrowDown","ArrowUp","Home","End"].includes(e.key))return;
  e.preventDefault();if(!open){setOpen(true);return;}
  const items=Array.from(surfaceRef.current?.querySelectorAll<HTMLButtonElement>('[role="option"]')??[]);
  const current=items.indexOf(document.activeElement as HTMLButtonElement);
  const next=e.key==="Home"?0:e.key==="End"?items.length-1:e.key==="ArrowDown"?Math.min(current+1,items.length-1):Math.max(current-1,0);
  items[next]?.focus();
 };
 return <div className="sm-choice" onKeyDown={keyboard}>
  <button ref={anchor} type="button" role="combobox" disabled={disabled} className={`sm-choice-trigger ${open?"is-open":""}`} aria-label={ariaLabel} aria-haspopup="listbox" aria-controls={open?id:undefined} aria-expanded={open} title={tooltip} data-testid={testId} data-value={value} onClick={()=>open?close():setOpen(true)}><span className="sm-choice-value">{selected?.icon}<span>{selected?.label??value}</span></span><ChevronDown size={16}/></button>
  {rawValue!==undefined&&value!==rawValue&&<button type="button" className="sm-choice-reset" disabled={disabled} aria-label="恢复默认值" onClick={()=>onChange(rawValue)}>↺</button>}
  {open&&<OverlayPortal><div ref={surfaceRef} className="sm-choice-menu" role="listbox" id={id} aria-label={`${ariaLabel}选项`} style={{...style,...layer}} data-placement={placement} data-testid={testId?`${testId}-menu`:undefined} onKeyDown={keyboard}>
   {searchable&&<label className="sm-choice-search"><Search size={16}/><input autoFocus value={query} onChange={e=>setQuery(e.target.value)} placeholder={searchPlaceholder}/></label>}
   <div className="sm-choice-options">
    {filtered.map(option=><button type="button" tabIndex={-1} role="option" title={[option.label??option.value,option.detail??option.group].filter(Boolean).join(" — ")} aria-selected={value===option.value} key={option.value} onClick={()=>{onChange(option.value);close();anchor.current?.focus();}}>{option.icon&&<span className="sm-choice-icon">{option.icon}</span>}<span className="sm-choice-copy"><strong>{option.label??option.value}</strong>{(option.detail||option.group)&&<small>{option.detail??option.group}</small>}</span>{value===option.value&&<Check size={16}/>}</button>)}
    {!filtered.length&&<p className="sm-choice-empty">没有匹配项</p>}
   </div>
  </div></OverlayPortal>}
 </div>;
}
