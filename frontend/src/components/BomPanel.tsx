"use client";

import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, List, GitBranch } from "lucide-react";
import { Bom, BomLineItem, BomTreeNode } from "@/lib/api";
import { MakeBuyBadge } from "@/components/Badges";

/** Fields every editable BOM row shares, whether rendered flat or inside the tree. The flat
 * list and the tree both pass through this one row + one edit handler - no forked edit logic. */
type EditableRow = {
  id: string;
  part_number: string;
  description: string;
  category: string;
  quantity: number;
  total_quantity?: number | null;
  material: string;
  make_buy: string;
  level: number;
};

function maxDepth(nodes: BomTreeNode[]): number {
  let deepest = 0;
  for (const n of nodes) {
    deepest = Math.max(deepest, n.level);
    if (n.children?.length) deepest = Math.max(deepest, maxDepth(n.children));
  }
  return deepest;
}

export interface BomPanelProps {
  bom: Bom;
  tree: { nodes: BomTreeNode[] } | null;
  onUpdate: (lineItemId: string, patch: Partial<BomLineItem>) => Promise<void> | void;
}

export default function BomPanel({ bom, tree, onUpdate }: BomPanelProps) {
  const depth = useMemo(() => (tree ? maxDepth(tree.nodes) : 0), [tree]);
  const [mode, setMode] = useState<"tree" | "flat">(depth > 1 ? "tree" : "flat");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  function toggleCollapsed(id: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="card p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold">
          Bill of Materials v{bom.version} &middot;{" "}
          <span className="text-steel-light font-normal">{bom.status}</span>
        </h2>
        <div className="flex items-center text-xs border border-border rounded-industrial overflow-hidden">
          <button
            className={`flex items-center gap-1 px-2 py-1 ${mode === "tree" ? "bg-ink text-white" : "bg-white"}`}
            onClick={() => setMode("tree")}
            disabled={!tree || tree.nodes.length === 0}
          >
            <GitBranch size={12} /> Tree view
          </button>
          <button
            className={`flex items-center gap-1 px-2 py-1 border-l border-border ${mode === "flat" ? "bg-ink text-white" : "bg-white"}`}
            onClick={() => setMode("flat")}
          >
            <List size={12} /> Flat view
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-steel border-b border-border text-left">
              <th className="py-1 pr-2 font-medium">Part</th>
              <th className="py-1 pr-2 font-medium">Description</th>
              <th className="py-1 pr-2 font-medium">Qty</th>
              <th className="py-1 pr-2 font-medium">Total Qty</th>
              <th className="py-1 pr-2 font-medium">Material</th>
              <th className="py-1 pr-2 font-medium">Make/Buy</th>
            </tr>
          </thead>
          <tbody>
            {mode === "tree" && tree && tree.nodes.length > 0 ? (
              <TreeRows nodes={tree.nodes} collapsed={collapsed} onToggle={toggleCollapsed} onUpdate={onUpdate} />
            ) : (
              bom.line_items
                .filter((li) => !li.parent_line_item_id || mode === "flat")
                .map((li) => (
                  <Row
                    key={li.id}
                    row={{
                      id: li.id,
                      part_number: li.part_number,
                      description: li.description,
                      category: li.category,
                      quantity: li.quantity,
                      material: li.material,
                      make_buy: li.make_buy,
                      level: 0,
                    }}
                    onUpdate={onUpdate}
                  />
                ))
            )}
          </tbody>
        </table>
        {bom.line_items.length === 0 && (
          <div className="text-sm text-steel text-center py-4">No line items yet.</div>
        )}
      </div>
    </div>
  );
}

function TreeRows({
  nodes,
  collapsed,
  onToggle,
  onUpdate,
}: {
  nodes: BomTreeNode[];
  collapsed: Set<string>;
  onToggle: (id: string) => void;
  onUpdate: BomPanelProps["onUpdate"];
}) {
  return (
    <>
      {nodes.map((node) => (
        <RowWithChildren key={node.id} node={node} collapsed={collapsed} onToggle={onToggle} onUpdate={onUpdate} />
      ))}
    </>
  );
}

function RowWithChildren({
  node,
  collapsed,
  onToggle,
  onUpdate,
}: {
  node: BomTreeNode;
  collapsed: Set<string>;
  onToggle: (id: string) => void;
  onUpdate: BomPanelProps["onUpdate"];
}) {
  const hasChildren = node.children && node.children.length > 0;
  const isCollapsed = collapsed.has(node.id);
  return (
    <>
      <Row
        row={{
          id: node.id,
          part_number: node.part_number,
          description: node.description,
          category: node.category,
          quantity: node.quantity,
          total_quantity: node.total_quantity,
          material: node.material,
          make_buy: node.make_buy,
          level: node.level,
        }}
        onUpdate={onUpdate}
        expandControl={
          hasChildren ? (
            <button
              className="inline-flex items-center justify-center w-4 h-4 mr-1 text-steel hover:text-ink"
              onClick={() => onToggle(node.id)}
              aria-label={isCollapsed ? "Expand" : "Collapse"}
            >
              {isCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
            </button>
          ) : (
            <span className="inline-block w-4 mr-1" />
          )
        }
      />
      {hasChildren && !isCollapsed && (
        <TreeRows nodes={node.children} collapsed={collapsed} onToggle={onToggle} onUpdate={onUpdate} />
      )}
    </>
  );
}

/** The single editable row used by both flat and tree rendering. Editing qty/material/make-buy
 * here calls the same onUpdate(lineItemId, patch) handler regardless of which view is active. */
function Row({
  row,
  onUpdate,
  expandControl,
}: {
  row: EditableRow;
  onUpdate: BomPanelProps["onUpdate"];
  expandControl?: React.ReactNode;
}) {
  return (
    <tr className="border-b border-border/60 last:border-0">
      <td className="py-1.5 pr-2 font-mono text-xs whitespace-nowrap">
        <span style={{ paddingLeft: row.level * 16 }} className="inline-flex items-center">
          {expandControl}
          {row.part_number || "(no part number)"}
        </span>
      </td>
      <td className="py-1.5 pr-2">{row.description}</td>
      <td className="py-1.5 pr-2">
        <input
          type="number"
          step="0.01"
          className="w-16 text-xs border border-border rounded px-1.5 py-1"
          defaultValue={row.quantity}
          onBlur={(e) => {
            const val = parseFloat(e.target.value);
            if (!Number.isNaN(val) && val !== row.quantity) onUpdate(row.id, { quantity: val });
          }}
        />
      </td>
      <td className="py-1.5 pr-2 text-xs text-steel">
        {row.total_quantity ?? <span className="text-steel-light">n/a</span>}
      </td>
      <td className="py-1.5 pr-2">
        <input
          type="text"
          className="w-28 text-xs border border-border rounded px-1.5 py-1"
          defaultValue={row.material}
          onBlur={(e) => {
            if (e.target.value !== row.material) onUpdate(row.id, { material: e.target.value });
          }}
        />
      </td>
      <td className="py-1.5 pr-2">
        <div className="flex items-center gap-2">
          <MakeBuyBadge value={row.make_buy} />
          <select
            className="text-xs border border-border rounded px-1.5 py-1"
            value={row.make_buy}
            onChange={(e) => onUpdate(row.id, { make_buy: e.target.value })}
          >
            <option>Make</option>
            <option>Buy</option>
            <option>Review</option>
          </select>
        </div>
      </td>
    </tr>
  );
}
