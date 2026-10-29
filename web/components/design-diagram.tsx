/**
 * Render editable design data as a local SVG diagram.
 * The subject page supplies a validated design response.
 * The browser does not execute model-generated markup.
 * Nodes and relationships are ordinary data.
 * Users may edit the JSON for their own scenario.
 * Invalid edits leave the previous preview visible.
 * SVG output can be downloaded for later editing.
 * The diagram stays in browser memory.
 * It is not published to a diagram service.
 * Use case and class relationships have explicit endpoints.
 * Include arrows point to the included use case.
 * Extend arrows point to the base use case.
 * Composition diamonds sit on the whole end.
 * Aggregation diamonds sit on the whole end.
 * Generalization arrows point to the parent class.
 * Dependency arrows point to the supplier.
 * WBS boxes display activity and planning fields.
 * Schedule bars use relative days.
 * Labels are rendered as text, never HTML.
 * React escapes user and model text.
 * No external rendering dependency is needed.
 * The layout uses a scrollable SVG viewport.
 * The model selects the design content.
 * The backend supplies note citations separately.
 * The subject page displays those citations.
 * Strict and normal modes remain separate.
 * The component does not request credentials.
 * The component makes no network calls.
 * Export uses a browser-created blob.
 * The blob is released after download.
 * The editor is accessible by keyboard.
 * Live edits require valid JSON.
 * Run npm test for frontend tests.
 * Run npm run build for production validation.
 */
"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { designMarkers, type DesignDiagram } from "@/lib/api";

export function DesignDiagramView({ initial }: { initial: DesignDiagram }) {
  const [diagram, setDiagram] = useState(initial);
  const [text, setText] = useState(JSON.stringify(initial, null, 2));
  const [error, setError] = useState("");
  const svg = useRef<SVGSVGElement>(null);
  function apply() {
    try {
      const value = JSON.parse(text) as DesignDiagram;
      if (!Array.isArray(value.nodes) || !value.nodes.length || !Array.isArray(value.edges)) throw new Error();
      setDiagram(value); setError("");
    } catch { setError("Enter valid diagram JSON with nodes and edges."); }
  }
  function download() {
    if (!svg.current) return;
    const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(svg.current)], { type: "image/svg+xml" }));
    const link = document.createElement("a"); link.href = url; link.download = "design.svg"; link.click();
    URL.revokeObjectURL(url);
  }
  const width = 900;
  const height = Math.max(180, diagram.nodes.length * 145 + 70);
  const positions = new Map(diagram.nodes.map((node, index) => [node.id, { x: 220 + (index % 2) * 430, y: 80 + index * 145 }]));
  return <div className="mt-4 space-y-3">
    <div className="overflow-auto rounded border bg-white"><svg ref={svg} xmlns="http://www.w3.org/2000/svg" viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label={diagram.title}>
      <defs><marker id="design-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#263d59" /></marker><marker id="design-diamond" viewBox="0 0 12 10" refX="1" refY="5" markerWidth="12" markerHeight="10" orient="auto-start-reverse"><path d="M 1 5 L 6 1 L 11 5 L 6 9 z" fill="#263d59" stroke="#263d59" /></marker><marker id="design-open-diamond" viewBox="0 0 12 10" refX="1" refY="5" markerWidth="12" markerHeight="10" orient="auto-start-reverse"><path d="M 1 5 L 6 1 L 11 5 L 6 9 z" fill="white" stroke="#263d59" /></marker></defs>
      <text x="24" y="28" fontSize="19" fontWeight="bold">{diagram.title}</text>
      {diagram.kind === "schedule" && diagram.nodes.map((node, index) => { const maxDay = Math.max(...diagram.nodes.map(item => item.start + item.days), 1); const dependencies = diagram.edges.filter(edge => edge.target === node.id).map(edge => diagram.nodes.find(item => item.id === edge.source)?.label || edge.source); return <g key={`bar-${node.id}`}><text x="25" y={70 + index * 145} fontSize="12">{node.label} · day {node.start + 1} · {node.days} days</text><rect x={25 + node.start / maxDay * 800} y={80 + index * 145} width={Math.max(2, node.days / maxDay * 800)} height="22" fill="#263d59" />{dependencies.length > 0 && <text x="25" y={120 + index * 145} fontSize="11">After: {dependencies.join(", ")}</text>}</g>; })}
      {diagram.kind !== "schedule" && diagram.edges.map((edge, index) => { const a = positions.get(edge.source); const b = positions.get(edge.target); if (!a || !b) return null; const dx = b.x - a.x, dy = b.y - a.y; const from = Math.min(150 / Math.abs(dx || 0.001), (dy > 0 && diagram.kind === "wbs" ? 75 : 40) / Math.abs(dy)); const to = Math.min(150 / Math.abs(dx || 0.001), (dy < 0 && diagram.kind === "wbs" ? 75 : 40) / Math.abs(dy)); const x1 = a.x + dx * from, y1 = a.y + dy * from, x2 = b.x - dx * to, y2 = b.y - dy * to; const markers = designMarkers(edge.kind); return <g key={index}><line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#263d59" strokeWidth="2" strokeDasharray={["include", "extend", "dependency"].includes(edge.kind) ? "6 4" : undefined} markerStart={markers.start ? `url(#design-${markers.start})` : undefined} markerEnd={markers.end ? `url(#design-${markers.end})` : undefined} /><text x={(x1 + x2) / 2} y={(y1 + y2) / 2} fontSize="12" fill="#263d59">{edge.kind === "include" || edge.kind === "extend" ? `«${edge.kind}»` : edge.kind === "child" ? "" : edge.kind}</text></g>; })}
      {diagram.kind !== "schedule" && diagram.nodes.map(node => { const p = positions.get(node.id)!; return <g key={node.id}>{node.kind === "usecase" ? <ellipse cx={p.x} cy={p.y} rx="150" ry="40" fill="#f8f5eb" stroke="#263d59" /> : <rect x={p.x - 150} y={p.y - 40} width="300" height={diagram.kind === "wbs" ? 115 : 80} rx="8" fill="#f8f5eb" stroke="#263d59" />}<text x={p.x} y={p.y - 20} textAnchor="middle" fontSize="14">{node.kind === "actor" ? `Actor: ${node.label}` : node.label}</text>{node.kind === "class" && <text x={p.x - 140} y={p.y - 4} fontSize="11">{(node.details || []).map((detail, index) => <tspan key={index} x={p.x - 140} dy="14">{detail}</tspan>)}</text>}{diagram.kind === "wbs" && <text x={p.x - 140} y={p.y + 8} fontSize="12"><tspan x={p.x - 140} dy="0">Activity: {node.activity}</tspan><tspan x={p.x - 140} dy="16">Resource: {node.resource}</tspan><tspan x={p.x - 140} dy="16">Cost: {node.cost}</tspan><tspan x={p.x - 140} dy="16">Duration: {node.duration}</tspan></text>}</g>; })}
    </svg></div>
    <Button type="button" variant="outline" size="sm" onClick={download}>Download SVG</Button>
    <details><summary className="cursor-pointer text-sm underline">Edit diagram JSON</summary><textarea aria-label="Diagram JSON" className="mt-2 h-64 w-full rounded border p-2 font-mono text-xs" value={text} onChange={event => setText(event.target.value)} /><Button type="button" size="sm" onClick={apply}>Update diagram</Button>{error && <p role="alert">{error}</p>}</details>
  </div>;
}
