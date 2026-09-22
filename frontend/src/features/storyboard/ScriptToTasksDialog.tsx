import { ArrowDown, ArrowUp, GitMerge, Plus, Scissors, Sparkles, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "terry-react-ui-library";

import type { Scene, TaskProposal } from "../../domain/storyboard";
import { Dialog, PortalSelect } from "../../ui/overlay";
import {
  mergeTaskProposals,
  proposalFromExcerpt,
  proposeTasksFromScript,
  splitTaskProposal,
} from "./scriptTaskProposals";

const sampleScript = `雨声渐密。林澜停在仓库门前，收起雨伞，伸手触碰生锈的门把。

门后的放映机自行启动。灰尘中的光束亮起，墙面出现不属于这个年代的旧影像。`;

function sceneLabel(number: string) {
  return number.replace(/^Scene\s*/i, "场景 ");
}

type ScriptToTasksDialogProps = {
  open: boolean;
  scenes: Scene[];
  defaultSceneId: string;
  onClose: () => void;
  onAccept: (proposals: TaskProposal[]) => void;
};

export function ScriptToTasksDialog({ open, scenes, defaultSceneId, onClose, onAccept }: ScriptToTasksDialogProps) {
  const [script, setScript] = useState(sampleScript);
  const [proposals, setProposals] = useState<TaskProposal[]>([]);
  const [message, setMessage] = useState("粘贴剧本后，可以让 AI 建议分镜边界，也可以手动选中一段添加。 ");
  const sequence = useRef(100);
  const scriptRef = useRef<HTMLTextAreaElement>(null);

  const nextTempId = () => {
    sequence.current += 1;
    return `proposal-local-${sequence.current}`;
  };

  const updateProposal = (tempId: string, patch: Partial<TaskProposal>) => {
    setProposals((current) => current.map((proposal) => proposal.tempId === tempId ? { ...proposal, ...patch } : proposal));
  };

  const createFromSelection = () => {
    const textarea = scriptRef.current;
    const selected = textarea?.value.slice(textarea.selectionStart, textarea.selectionEnd).trim() ?? "";
    if (!selected) {
      setMessage("请先在剧本文本中选中一段内容。");
      return;
    }
    setProposals((current) => [...current, proposalFromExcerpt(selected, nextTempId(), defaultSceneId)]);
    setMessage("已添加一个分镜建议。");
  };

  const generateMockProposals = () => {
    const generated = proposeTasksFromScript(script, defaultSceneId).map((proposal) => ({ ...proposal, tempId: nextTempId() }));
    setProposals(generated);
    setMessage(generated.length > 0 ? `AI 建议了 ${generated.length} 个分镜。请快速确认边界和顺序。` : "请先粘贴剧本内容。");
  };

  const moveProposal = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= proposals.length) return;
    setProposals((current) => {
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const mergeWithNext = (index: number) => {
    if (!proposals[index + 1]) return;
    setProposals((current) => [
      ...current.slice(0, index),
      mergeTaskProposals(current[index], current[index + 1]),
      ...current.slice(index + 2),
    ]);
  };

  const splitProposal = (index: number) => {
    const split = splitTaskProposal(proposals[index]);
    if (!split) {
      setMessage("这段内容暂时没有合适的拆分位置。");
      return;
    }
    setProposals((current) => [...current.slice(0, index), ...split, ...current.slice(index + 1)]);
  };

  const acceptOne = (proposal: TaskProposal) => {
    onAccept([proposal]);
    setProposals((current) => current.filter((item) => item.tempId !== proposal.tempId));
    setMessage("已创建 1 个分镜。");
  };

  return (
    <Dialog
      open={open}
      size="wide"
      icon="script" title="从剧本创建分镜"
      description="先确认分镜边界和顺序；镜头细节、提示词和生成参数稍后再编辑。"
      onClose={onClose}
    >
      <div className="script-task-dialog director-script-import">
        <section className="script-task-source">
          <label htmlFor="script-task-source">剧本文本</label>
          <textarea
            id="script-task-source"
            ref={scriptRef}
            value={script}
            onChange={(event) => setScript(event.target.value)}
            rows={10}
          />
          <div>
            <Button onClick={createFromSelection}><Plus size={14} /> 从选中段落添加</Button>
            <Button variant="accent" onClick={generateMockProposals}><Sparkles size={14} /> AI 建议分镜</Button>
          </div>
          <p role="status">{message}</p>
        </section>

        <section className="script-task-proposals director-shot-suggestions" aria-label="分镜建议">
          <header><strong>分镜建议</strong><span>{proposals.length}</span></header>
          {proposals.length === 0 ? (
            <div className="script-task-empty">还没有分镜建议。</div>
          ) : proposals.map((proposal, index) => (
            <article key={proposal.tempId} aria-label={`分镜建议 ${index + 1}`}>
              <header>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{proposal.plannedDurationSeconds} 秒</strong>
                {proposal.visualBeats.length > 1 && <em>{proposal.visualBeats.length} 个内部镜头</em>}
                <button type="button" aria-label={`上移分镜建议 ${index + 1}`} onClick={() => moveProposal(index, -1)} disabled={index === 0}><ArrowUp size={13} /></button>
                <button type="button" aria-label={`下移分镜建议 ${index + 1}`} onClick={() => moveProposal(index, 1)} disabled={index === proposals.length - 1}><ArrowDown size={13} /></button>
              </header>

              <label>
                <span>分镜标题</span>
                <input value={proposal.title} onChange={(event) => updateProposal(proposal.tempId, { title: event.target.value })} />
              </label>

              <div className="director-suggestion-excerpt">{proposal.scriptExcerpt}</div>

              <div className="script-task-proposal-row director-suggestion-row">
                <label>
                  <span>时长</span>
                  <input
                    type="number"
                    min="1"
                    value={proposal.plannedDurationSeconds}
                    onChange={(event) => updateProposal(proposal.tempId, { plannedDurationSeconds: Math.max(1, Number(event.target.value) || 1) })}
                  />
                </label>
                <label>
                  <span>放到场景</span>
                  <PortalSelect
                    value={proposal.targetSceneId}
                    onChange={(targetSceneId) => updateProposal(proposal.tempId, { targetSceneId })}
                    ariaLabel={`分镜建议 ${index + 1} 目标场景`}
                    options={scenes.map((scene) => ({ value: scene.id, label: `${sceneLabel(scene.number)} · ${scene.title}` }))}
                  />
                </label>
              </div>

              <footer>
                <button type="button" onClick={() => splitProposal(index)}><Scissors size={13} /> 拆开</button>
                <button type="button" onClick={() => mergeWithNext(index)} disabled={index === proposals.length - 1}><GitMerge size={13} /> 合并下一条</button>
                <button type="button" onClick={() => setProposals((current) => current.filter((item) => item.tempId !== proposal.tempId))}><Trash2 size={13} /> 删除</button>
                <Button variant="accent" onClick={() => acceptOne(proposal)}>创建分镜</Button>
              </footer>
            </article>
          ))}
        </section>

        <footer className="script-task-dialog-actions">
          <Button onClick={onClose}>取消</Button>
          <Button
            variant="accent"
            disabled={proposals.length === 0}
            onClick={() => {
              onAccept(proposals);
              setProposals([]);
              onClose();
            }}
          >创建全部 {proposals.length} 个分镜</Button>
        </footer>
      </div>
    </Dialog>
  );
}