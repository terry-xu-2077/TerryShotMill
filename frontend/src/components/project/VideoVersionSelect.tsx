import { useEffect, useState } from "react";
import { Select } from "../../ui/Select";
import { httpProjectGateway, type VideoResultVersion } from "../../gateways/projectGateway";

export function VideoVersionSelect({projectId, taskId, resultId, onChanged}: {projectId:string;taskId:string;resultId?:string;onChanged?:()=>Promise<void>}) {
  const [versions, setVersions] = useState<VideoResultVersion[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setVersions([]); setError("");
    httpProjectGateway.getVideoVersions(projectId, taskId).then(data => {
      if (active) setVersions([...data.items].sort((a,b)=>Date.parse(b.createdAt)-Date.parse(a.createdAt)));
    }).catch(()=> { if (active) setError("视频版本读取失败"); });
    return () => {active = false;};
  }, [projectId, taskId, resultId]);
  return <div className="task-video-versions"><Select ariaLabel="视频历史版本" value={resultId ?? ""} disabled={busy || !versions.length} options={versions.length ? versions.map((item,index)=>({value:item.id,label:`版本 ${versions.length-index} · ${new Date(item.createdAt).toLocaleString()}`})) : [{value:"",label:"暂无视频版本"}]} onChange={async id=> {
    if (busy || id === resultId) return;
    setBusy(true); setError("");
    try { await httpProjectGateway.selectVideoVersion(projectId, taskId, id); await onChanged?.(); }
    catch {setError("版本切换未确认，请重试");}
    finally {setBusy(false);}
  }} />{busy && <span role="status">正在切换…</span>}{error && <span role="alert">{error}</span>}</div>;
}
