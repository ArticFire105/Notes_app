/**
 * Upload and read private worksheets for one subject.
 * Each worksheet is saved before its answers are generated.
 * The backend reads all worksheet pages together.
 * Questions are answered separately in their original order.
 * Answers appear as soon as they are stored.
 * Progress is calculated from saved question statuses.
 * A failed question has its own retry button.
 * The selected answer mode is saved with the worksheet.
 * Both modes require evidence from course documents.
 * Document and page citations accompany supported answers.
 * Missing evidence is clearly reported by the backend.
 * Worksheet content is private to the signed-in student.
 * The backend enforces access before returning records.
 * Database row security provides a second protection.
 * PDFs and images are sent to Google for extraction.
 * The interface explains this before the student uploads.
 * Uploading must finish before navigating away.
 * Background processing continues after navigation.
 * Returning to the subject reloads saved worksheets.
 * This component polls while a worksheet is processing.
 * The quiz feature remains postponed.
 * A user key can be supplied through the session client.
 * Keys are never written to browser storage by this component.
 * Requests go through the existing API client.
 * Server errors are shown as safe messages.
 * Extracted metadata can be used in a later quiz.
 * Original question order is kept.
 * The student may select several photos as one worksheet.
 * Each photo contributes to one extraction request.
 * The backend checks file type and size.
 * A PDF may contain several pages.
 * This component does not store the source images.
 * The existing subject page provides the subject ID.
 * Use the backend tests and web build for verification.
 */
"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, errorMessage, type Worksheet, type WorksheetDetail, type Source } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function Markdown({ text }: { text: string }) {
  return <div className="space-y-2 overflow-x-auto break-words text-sm [&_h1]:mt-4 [&_h1]:font-semibold [&_h2]:mt-4 [&_h2]:font-semibold [&_h3]:mt-3 [&_h3]:font-semibold [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:p-2 [&_td]:border [&_td]:p-2 [&_pre]:overflow-x-auto">
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ img: () => null }}>{text}</ReactMarkdown>
  </div>;
}

export function Worksheets({ subjectId, selected, select, answerMethod }: { subjectId: number; selected: string; select: (id: string) => void; answerMethod: string }) {
  const [list, setList] = useState<Worksheet[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [mode, setMode] = useState("normal");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function refresh() { setList(await api.worksheets(subjectId)); }
  useEffect(() => { void refresh().catch(e => setError(errorMessage(e))); }, [subjectId]);
  async function remove(id: string) {
    if (!window.confirm("Delete this worksheet and all its questions and conversations?")) return;
    setError("");
    try { await api.deleteWorksheet(id); if (selected === id) select(""); await refresh(); }
    catch (e) { setError(errorMessage(e)); }
  }
  async function upload(event: React.FormEvent) {
    event.preventDefault();
    if (!files.length) return;
    setBusy(true); setError("");
    const data = new FormData();
    data.set("subject_id", String(subjectId)); data.set("mode", mode); data.set("answer_method", answerMethod);
    files.forEach(file => data.append("files", file));
    try { const result = await api.uploadWorksheet(data); await refresh(); select(result.id); setFiles([]); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  return <Card><CardHeader><CardTitle>Worksheets</CardTitle></CardHeader><CardContent className="space-y-3">
    <p className="text-xs">PDFs and photos are sent to Google Gemini. Stay until upload finishes; processing continues after you leave.</p>
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    <form onSubmit={upload} className="space-y-2"><input aria-label="Worksheet files" type="file" multiple accept=".pdf,.png,.jpg,.jpeg" onChange={e => setFiles(Array.from(e.target.files || []))} className="w-full text-xs" /><label className="block text-xs">Answer mode <select value={mode} onChange={e => setMode(e.target.value)}><option value="normal">Normal</option><option value="strict">Strict</option></select></label><Button disabled={busy || !files.length} size="sm">{busy ? "Uploading..." : "Upload worksheet"}</Button></form>
    {list.length > 0 && <label className="block text-xs">Open worksheet <select className="w-full" value={selected} onChange={e => select(e.target.value)}><option value="">Choose a worksheet</option>{list.map(item => <option key={item.id} value={item.id}>{new Date(item.created_at).toLocaleString()} - {item.status}</option>)}</select></label>}
    {list.map(item => <div key={item.id} className="flex items-center gap-2 text-xs"><span className="min-w-0 flex-1 truncate">{new Date(item.created_at).toLocaleString()}</span><Button type="button" size="sm" variant="outline" onClick={() => void remove(item.id)}>Delete</Button></div>)}
  </CardContent></Card>;
}

export function WorksheetChat({ selected, answerMethod, setAnswerMethod, openSource, Figure }: { selected: string; answerMethod: string; setAnswerMethod: (value: string) => void; openSource: (source: Source) => void; Figure: React.ComponentType<{id: string}> }) {
  const [detail, setDetail] = useState<WorksheetDetail | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [focus, setFocus] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setDetail(null); setFocus("");
    if (!selected) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try { const value = await api.worksheet(selected); if (active) setDetail(value); }
      catch (e) { if (active) setError(errorMessage(e)); }
      if (active) timer = setTimeout(() => void poll(), 3000);
    }
    void poll(); return () => { active = false; clearTimeout(timer); };
  }, [selected]);
  useEffect(() => {
    if (selected && answerMethod === "all" && detail?.status === "ready" && detail.questions.some(q => q.status === "queued")) {
      void api.answerWorksheet(selected).catch(e => setError(errorMessage(e)));
    }
  }, [selected, answerMethod, detail?.status]);
  async function start(id?: number) {
    try { if (id) await api.retryWorksheetQuestion(selected, id); else await api.answerWorksheet(selected); setDetail(await api.worksheet(selected)); }
    catch (e) { setError(errorMessage(e)); }
  }
  async function ask(event: React.FormEvent) {
    event.preventDefault();
    if (!message.trim()) return;
    setBusy(true); setError("");
    try { await api.askWorksheet(selected, focus ? Number(focus) : null, message); setMessage(""); setDetail(await api.worksheet(selected)); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  if (!selected) return <p className="p-6 text-sm">Choose a worksheet in the side panel.</p>;
  if (!detail) return <p className="p-6 text-sm">Loading worksheet...</p>;
  const done = detail.questions.filter(q => q.status === "ready").length;
  const visible = detail.questions.filter(q => filter === "unanswered" ? q.status !== "ready" : filter === "three" ? Number(q.marks) === 3 : true);
  const next = detail.questions.find(q => q.status === "queued" || q.status === "failed");
  return <div className="space-y-4 p-5" aria-live="polite">
    <div className="flex flex-wrap items-center gap-2"><span className="text-sm font-medium">Answered {done} / {detail.questions.length}</span><progress className="min-w-28 flex-1" value={done} max={detail.questions.length || 1} /></div>
    {detail.status === "extracting" && <p>Reading questions...</p>}{detail.error && <p role="alert" className="text-sm text-red-700">{detail.error}</p>}{error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    <label className="text-sm">Processing <select value={answerMethod} onChange={e => setAnswerMethod(e.target.value)}><option value="one">One by one</option><option value="all">All at once</option></select></label>
    <div className="flex flex-wrap gap-2">{["Answer all questions", "Help me solve this one", "Which question would you like to know?", "Explain question 4 step by step", "Give me only the 3-mark answers", "Show questions I haven't answered yet"].map(chip => <Button key={chip} size="sm" variant="outline" type="button" onClick={() => { if (chip === "Answer all questions") void start(); else if (chip.includes("3-mark")) setFilter("three"); else if (chip.includes("haven't")) setFilter("unanswered"); else { setFilter("all"); if (chip.includes("question 4")) { const q = detail.questions.find(item => item.question_number === "4"); if (q) setFocus(String(q.id)); setMessage("Explain this step by step"); } } }}>{chip}</Button>)}<Button type="button" size="sm" variant="outline" onClick={() => setFilter("all")}>Show all</Button>{answerMethod === "one" && next && <Button type="button" size="sm" onClick={() => void start(next.id)}>Next</Button>}</div>
    {visible.map(q => <details key={q.id} className="rounded-lg border bg-white p-3" open><summary className="cursor-pointer font-semibold">{q.question_number ? `Question ${q.question_number}` : `Question ${q.position}`} {q.marks != null && <span className="text-xs">{q.marks} marks</span>} {q.question_type && <span className="text-xs uppercase">{q.question_type}</span>} <span className="text-xs font-normal">{q.status === "queued" ? "waiting" : q.status === "ready" ? "done" : q.status}</span></summary><p className="mt-2 whitespace-pre-wrap font-semibold">{q.question_text}</p>{q.answer && <div className="mt-3"><Markdown text={q.answer} /></div>}{q.sources?.map(source => <div key={source.n}><button className="mt-2 rounded border px-2 py-1 text-xs underline" onClick={() => openSource(source)}>[{source.n}] {source.document} - {source.page_label}</button>{source.figure_id && <Figure id={source.figure_id} />}</div>)}{(q.status === "failed" || q.status === "queued") && <Button type="button" size="sm" variant="outline" className="mt-2" onClick={() => void start(q.id)}>{q.status === "failed" ? "Retry" : "Answer"}</Button>}{q.error && <p className="text-xs text-red-700">{q.error}</p>}{detail.chat.filter(turn => turn.question_id === q.id).map(turn => <div key={turn.id} className="mt-3 border-t pt-3"><p className="font-semibold">{turn.message}</p><Markdown text={turn.answer} />{turn.sources.map(source => <button key={source.n} onClick={() => openSource(source)} className="block text-xs underline">[{source.n}] {source.document} - {source.page_label}</button>)}</div>)}</details>)}
    <form onSubmit={ask} className="space-y-2 border-t pt-4"><label className="block text-xs">Question shortcut (optional) <select value={focus} onChange={e => setFocus(e.target.value)}><option value="">Select question</option>{detail.questions.map(q => <option key={q.id} value={q.id}>Question {q.question_number || q.position}</option>)}</select></label><textarea aria-label="Question about worksheet" value={message} onChange={e => setMessage(e.target.value)} className="w-full rounded border p-2 text-sm" placeholder="Explain this question more simply..." /><Button disabled={busy || !message.trim()} type="submit">Ask</Button></form>
    {detail.chat.filter(turn => turn.question_id === null).map(turn => <div key={turn.id} className="rounded-lg border p-3 text-sm"><p className="mb-2 font-semibold">{turn.message}</p><Markdown text={turn.answer} />{turn.sources.map(source => <button key={source.n} onClick={() => openSource(source)} className="block text-xs underline">[{source.n}] {source.document} - {source.page_label}</button>)}</div>)}
  </div>;
}
