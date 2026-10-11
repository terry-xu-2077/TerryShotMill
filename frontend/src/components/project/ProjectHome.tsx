import { useEffect, useState, type ReactNode } from "react";
import { Check, FolderOpen, Plus } from "lucide-react";
import { BrandPlaceholder } from "../../ui/branding/BrandPlaceholder";
import { BrandLogo } from "../../ui/branding/BrandLogo";
import { TaskNewResults, useViewedResults } from "./TaskNewResults";
import { TaskRiskSticker } from "./TaskRiskSticker";
import type { ProjectSummary } from "../../gateways/projectGateway";
import { Button } from "../../ui/primitives";
import { Dialog } from "../../ui/overlay";
import { ThemeSwitch } from "../../ui/ThemeSwitch";

export function ProjectHome({ bridgeStatus, projects, loading = false, error = "", onRetry, onOpenProject, onCreateProject, onOpenProjectFile, onManageProjects, onImportProject }: {
  bridgeStatus?: ReactNode;
  projects: ProjectSummary[]; loading?: boolean; error?: string; onRetry?: () => void;
  onOpenProject: (projectId: string) => void; onCreateProject: () => void;
  onOpenProjectFile?: () => void;
  onManageProjects?: () => void;
  onImportProject?: () => void;
}) {
  const { unread } = useViewedResults();
  return <main className="project-home" aria-label="项目首页">
    <header className="project-home-title"><h1><BrandLogo />Terry导演工作台</h1>{bridgeStatus}<ThemeSwitch /></header>
    <div className="project-home-collection">
      <header className="project-collection-heading"><h2>项目</h2><span className="project-home-count">{projects.length} 个项目</span>{onOpenProjectFile && <Button onClick={onOpenProjectFile}><FolderOpen size={14} /> 打开工程</Button>}{onImportProject && <Button onClick={onImportProject}>导入项目</Button>}{onManageProjects && <Button onClick={onManageProjects}>项目管理</Button>}</header>
      {error && projects.length > 0 && <p className="project-file-error" role="alert">{error}</p>}
      <svg width="0" height="0" aria-hidden="true" style={{ position: "absolute" }}><defs>
        <clipPath id="project-folder-outline" clipPathUnits="objectBoundingBox"><path d="M0 .15 Q0 0 .06 0 H.32 C.36 0 .36 .13 .42 .13 H.94 Q1 .13 1 .27 V.87 Q1 1 .94 1 H.06 Q0 1 0 .87 Z" /></clipPath>
      </defs></svg>
      <section className="project-folder-grid" aria-label="项目列表">
        <button type="button" className="project-folder-card project-create-card" onClick={onCreateProject}><div><Plus className="creation-motion-icon" size={30} /><span>新建项目</span></div></button>
        {loading && projects.length === 0 && <div className="project-folder-card project-create-card" role="status">正在加载项目…</div>}
        {!loading && error && projects.length === 0 && <button type="button" className="project-folder-card project-create-card" onClick={onRetry}><div><span>项目加载失败，点击重试</span></div></button>}
        {projects.map(project => {
          const kinds = [...new Set((project.newResults ?? []).flatMap(unread))];
          return <div key={project.id} className="project-folder-item">
            <button type="button" className={`project-folder-card is-${project.status} ${project.coverUrl ? "has-cover" : "is-empty"}`} onClick={() => onOpenProject(project.id)} aria-label={`打开项目 ${project.title}`}>
              {project.coverUrl && <><div className="project-folder-sheet project-folder-paper" aria-hidden="true" /><div className="project-folder-sheet project-folder-paper-middle" aria-hidden="true" /></>}
              <div className="project-folder-sheet project-folder-cover" style={project.coverUrl ? { backgroundImage: `url("${project.coverUrl}")` } : undefined}>{!project.coverUrl && <BrandPlaceholder />}</div>
              <div className="project-folder-front">
                <div className="project-folder-tab"><time className="project-folder-date" dateTime={project.createdAt}>{project.createdAt ? new Date(project.createdAt).toLocaleDateString("zh-CN") : ""}</time></div>
                <h2>{project.title}</h2><p className="project-folder-description">{project.description || "暂无项目简介"}</p>
                <footer><span>{project.taskCount} 个任务</span><span>{project.assetCount} 个资产</span><span>已生成 {project.completedTaskCount ?? 0}/{project.taskCount}</span></footer>
              </div>
            </button><div className="project-folder-notices"><TaskNewResults kinds={kinds} /><TaskRiskSticker warnings={project.generationWarnings ?? []} /></div>
          </div>;
        })}
      </section>
    </div>
  </main>;
}

export function CreateProjectDialog({
  open,
  onClose,
  onCreate,
  onBrowsePath,
  error = "",
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (title: string, path: string) => void;
  onBrowsePath?: () => Promise<string | null>;
  error?: string;
}) {
  const [title, setTitle] = useState("");
  const [path, setPath] = useState("");

  useEffect(() => {
    if (open) { setTitle(""); setPath(""); }
  }, [open]);

  return (
    <Dialog open={open} icon="create" title="新建项目" description="创建后进入项目工作台。" onClose={onClose}>
      <div className="project-simple-dialog">
        <label><span>项目名称</span><input autoFocus value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：异星边境 初到基地" /></label>
        <label htmlFor="create-project-path"><span>工程文件位置</span></label><div className="project-file-row"><input id="create-project-path" value={path} onChange={(event) => setPath(event.target.value)} placeholder="选择或输入 .shotmill 文件路径" />{onBrowsePath && <Button onClick={() => void onBrowsePath().then(value => { if (value) setPath(value); })}>浏览…</Button>}</div>
        {error && <p className="project-file-error" role="alert">{error}</p>}
        <footer>
          <Button onClick={onClose}>取消</Button>
          <Button variant="accent" disabled={!title.trim() || !path.trim()} onClick={() => onCreate(title.trim(), path.trim())}><Check size={14} /> 创建项目</Button>
        </footer>
      </div>
    </Dialog>
  );
}

export function OpenProjectDialog({ open, onClose, onOpen, onBrowsePath, error = "" }: {
  open: boolean;
  onClose: () => void;
  onOpen: (path: string) => void;
  onBrowsePath?: () => Promise<string | null>;
  error?: string;
}) {
  const [path, setPath] = useState("");
  useEffect(() => { if (open) setPath(""); }, [open]);
  return <Dialog open={open} icon="create" title="打开工程" onClose={onClose}>
    <div className="project-simple-dialog">
      <label htmlFor="open-project-path"><span>工程文件位置</span></label><div className="project-file-row"><input id="open-project-path" autoFocus value={path} onChange={event => setPath(event.target.value)} placeholder="选择 .shotmill 工程文件" />{onBrowsePath && <Button onClick={() => void onBrowsePath().then(value => { if (value) setPath(value); })}>浏览…</Button>}</div>
      {error && <p className="project-file-error" role="alert">{error}</p>}
      <footer><Button onClick={onClose}>取消</Button><Button variant="accent" disabled={!path.trim()} onClick={() => onOpen(path.trim())}>打开</Button></footer>
    </div>
  </Dialog>;
}
