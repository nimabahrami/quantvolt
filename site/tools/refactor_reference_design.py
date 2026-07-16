#!/usr/bin/env python3
"""Idempotently apply and audit the API-reference description design system.

The static site has one renderer for every generated symbol. This tool changes that
renderer rather than rewriting generated API records, then verifies that fields,
parameters, members, methods, descriptions, and errors all receive semantic classes.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "script.js"
CSS = ROOT / "enhancements.css"

REPLACEMENTS = {
    "fields": (
        "`<div><code>${esc(field.name)}</code><p><span class=\"type-label\">${esc(field.type)}</span>",
        "`<div class=\"doc-row variable-row\"><code class=\"doc-name\">${esc(field.name)}</code><p><span class=\"type-label\">${esc(field.type)}</span>",
    ),
    "members": (
        "`<div><code>${esc(member.name)}</code><p>${esc(member.value)}</p></div>`",
        "`<div class=\"doc-row variable-row\"><code class=\"doc-name\">${esc(member.name)}</code><p><code class=\"member-value\">${esc(member.value)}</code></p></div>`",
    ),
    "methods": (
        "`<div><code>${esc(method.signature)}</code><p>${inlineDoc(method.summary || 'Public method.')}</p></div>`",
        "`<div class=\"method-card\"><code class=\"method-signature\">${esc(method.signature)}</code><p>${inlineDoc(method.summary || 'Public method.')}</p></div>`",
    ),
    "description": (
        "<h2 id=\"description\">Description</h2><div class=\"api-description\">${doc}</div>${fields}",
        "<h2 id=\"description\">Description</h2>${doc}${fields}",
    ),
    "fallback-description": (
        "`<p>This public ${symbol.kind} is exported by <code>${moduleByName(moduleName)?.qualified}</code>. See the source for implementation details and validation behavior.</p>`",
        "`<div class=\"api-description\"><p>This public ${symbol.kind} is exported by <code>${moduleByName(moduleName)?.qualified}</code>. See the source for implementation details and validation behavior.</p></div>`",
    ),
    "not-found": (
        "`<p><a href=\"#/overview\">Return to the overview →</a></p>`,'404'",
        "`<div class=\"admonition error\" role=\"alert\"><b>Documentation error</b><p>The requested route does not match a generated guide or API symbol.</p><a href=\"#/overview\">Return to the overview →</a></div>`,'404'",
    ),
}

DOC_RENDERER = r'''function renderDoc(doc){
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
}'''

INLINE_RENDERER = r'''function inlineDoc(value){
  return esc(value)
    .replace(/``([^`]+)``/g,'<code>$1</code>')
    .replace(/:(?:class|func|meth|attr|mod|data|exc|const):`~?([^`]+)`/g,'<code>$1</code>')
    .replace(/`([^`]+)`/g,'<code>$1</code>');
}'''

CSS_BLOCK = r"""

/* API description system — maintained by tools/refactor_reference_design.py */
:root{
  --error:#CA3535;
  --error-soft:color-mix(in srgb,var(--error) 8%,var(--bg));
  --error-border:color-mix(in srgb,var(--error) 58%,var(--border));
  --variable-border:color-mix(in srgb,var(--brand-ink) 24%,var(--brand-gray));
  --variable-fill:transparent;
}
.api-description{max-width:820px;padding:18px 20px;border-left:3px solid var(--brand-blue);background:color-mix(in srgb,var(--brand-gray) 23%,transparent);border-radius:0 7px 7px 0}
.api-description>p:first-child{margin-top:0}.api-description>p:last-child{margin-bottom:0}
.doc-table{display:grid;gap:9px;border:0;background:transparent;overflow:visible}
.doc-table>.doc-row{display:grid;grid-template-columns:minmax(150px,220px) 1fr;gap:18px;padding:13px 15px;border:1px solid var(--variable-border);border-radius:7px;background:var(--variable-fill)}
.doc-table>.doc-row:last-child{border:1px solid var(--variable-border)}
.doc-name,.member-value,.method-signature{font-family:var(--mono);font-variant-ligatures:none}
.doc-name{color:var(--brand-ink);font-weight:650;overflow-wrap:anywhere}
.type-label{display:inline-block;color:color-mix(in srgb,var(--brand-teal) 72%,var(--brand-ink));font-family:var(--mono);font-size:.94em}
.method-list{display:grid;gap:10px;border:0;background:transparent}
.method-list>.method-card{padding:15px 17px;border:1px solid var(--variable-border);border-radius:7px;background:var(--variable-fill)}
.method-list>.method-card:last-child{border:1px solid var(--variable-border)}
.method-signature{display:block;color:var(--brand-blue);font-size:12px;font-weight:650;line-height:1.65;overflow-wrap:anywhere}
.method-card p{padding-top:9px;margin-top:9px;border-top:1px solid var(--border)}
.error-table>.error-row{position:relative;border-color:var(--error-border);background:var(--error-soft)}
.error-table>.error-row::before{content:"!";position:absolute;left:-9px;top:13px;display:grid;place-items:center;width:18px;height:18px;border-radius:50%;background:var(--error);color:white;font:700 11px var(--sans)}
.error-row .doc-name,.admonition.error b{color:var(--error)}
.admonition.error{border-left:4px solid var(--error);background:var(--error-soft)}
.admonition.error a{font-weight:650}
.exception-tree{border:0;background:transparent;padding:4px 0}
.exception-tree div{border-left:1px solid var(--border)}
.exception-tree code{border:1px solid var(--error);background:transparent;color:var(--text);box-shadow:none}
.dark{--error:#FF7B7B;--error-soft:color-mix(in srgb,var(--error) 10%,var(--bg));--variable-border:color-mix(in srgb,var(--brand-gray) 26%,var(--brand-ink))}
.dark .doc-name{color:var(--brand-gray)}
@media(max-width:760px){.doc-table>.doc-row{grid-template-columns:1fr;gap:6px}.api-description{padding:15px 16px}}
"""

CSS_V2 = r"""

/* Structured API docstring sections — maintained by tools/refactor_reference_design.py */
.doc-section-note{padding:15px 17px;border:1px solid var(--variable-border);border-radius:7px;background:var(--variable-fill)}
.doc-section-note p{margin:0}
.doc-section-note.warning-note{border-left:4px solid var(--brand-teal);background:color-mix(in srgb,var(--brand-teal) 7%,var(--bg))}
.doc-section-note.error-note{border-left:4px solid var(--error);border-color:var(--error-border);background:var(--error-soft)}
"""


def replace_once(text: str, name: str, old: str, new: str) -> tuple[str, str]:
    if new in text:
        return text, "already applied"
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{name}: expected exactly one source pattern, found {count}")
    return text.replace(old, new), "applied"


def main() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    outcomes: list[str] = []
    inline_start = script.index("function inlineDoc(value){")
    inline_end = script.index("\nfunction renderDoc", inline_start)
    current_inline = script[inline_start:inline_end]
    if current_inline != INLINE_RENDERER:
        script = script[:inline_start] + INLINE_RENDERER + script[inline_end:]
        outcomes.append("inline API references: applied")
    else:
        outcomes.append("inline API references: already applied")
    renderer_start = script.index("function renderDoc(doc){")
    renderer_end = script.index("\nfunction renderApiIndex", renderer_start)
    current_renderer = script[renderer_start:renderer_end]
    if current_renderer != DOC_RENDERER:
        script = script[:renderer_start] + DOC_RENDERER + script[renderer_end:]
        outcomes.append("docstring structure: applied")
    else:
        outcomes.append("docstring structure: already applied")
    for name, (old, new) in REPLACEMENTS.items():
        script, status = replace_once(script, name, old, new)
        outcomes.append(f"{name}: {status}")
    SCRIPT.write_text(script, encoding="utf-8")

    css = CSS.read_text(encoding="utf-8")
    marker = "/* API description system — maintained by tools/refactor_reference_design.py */"
    if marker not in css:
        css = css.rstrip() + CSS_BLOCK + "\n"
        outcomes.append("design tokens and components: applied")
    else:
        outcomes.append("design tokens and components: already applied")
    marker_v2 = "/* Structured API docstring sections — maintained by tools/refactor_reference_design.py */"
    if marker_v2 not in css:
        css = css.rstrip() + CSS_V2 + "\n"
        outcomes.append("structured docstring sections: applied")
    else:
        outcomes.append("structured docstring sections: already applied")
    CSS.write_text(css, encoding="utf-8")

    required_script = (
        "api-description", "variable-row", "error-row", "method-card",
        "method-signature", "admonition error", "Attributes:", "Yields:",
        "doc-section-note", "(?:class|func|meth|attr|mod|data|exc|const)",
    )
    required_css = (
        "--error:#CA3535", ".api-description", ".doc-table>.doc-row",
        ".method-list>.method-card", ".error-table>.error-row", ".admonition.error",
        ".doc-section-note",
    )
    missing = [token for token in required_script if token not in script]
    missing += [token for token in required_css if token not in css]
    if missing:
        raise RuntimeError("design audit failed; missing: " + ", ".join(missing))

    print("Reference design refactor complete")
    for outcome in outcomes:
        print(f"  {outcome}")
    print("  audit: fields, parameters, members, methods, descriptions, and errors covered")


if __name__ == "__main__":
    main()
