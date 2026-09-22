# Marketplace Plugin Documentation Standard

**Effective:** 2026-09-23  
**Status:** MANDATORY for all plugins (new and existing)  
**Enforcement:** Marketplace index validation + CI/CD gate

---

## Overview

Every plugin in the Corvin Marketplace MUST include professional, comprehensive documentation. This standard ensures consistency, discoverability, and usability across the entire ecosystem.

---

## Required Documentation

### 1. README.md (Landing Page)

**Location:** `plugins/buildin/<category>/<name>/README.md`

**Minimum Length:** 1,000 words (comprehensive coverage)

**Structure:**

```
# Plugin Name — One-line tagline

**Brief description (1–2 paragraphs) explaining what it does.**

---

## 🎯 What It Does

- **Feature 1:** Description
- **Feature 2:** Description
- **Feature 3:** Description

Perfect for: Use case 1, Use case 2, Use case 3

---

## ✨ Key Features

### 1. **Feature Name**
Detailed explanation (2–3 sentences)

### 2. **Feature Name**
Detailed explanation

### 3. **Feature Name**
Detailed explanation

---

## 🏗️ How It Works

### Architecture Overview
[Reference to SVG diagram: architecture.svg]

### Typical Workflow
[Reference to SVG diagram: flow.svg]

---

## 🚀 Quick Start

### Installation
```bash
# Command to install
```

### Basic Usage
```bash
# Real code example (runnable)
```

### Configuration
```yaml
# YAML config example
```

---

## 📊 Specifications

| Metric | Value |
|--------|-------|
| Supported Features | X, Y, Z |
| Performance | P50, P99 latency |
| Concurrency | Max requests/sec |
| Data Retention | Days/months |

---

## 🔒 Security & Compliance

- **Audit Trail:** Every action logged (hash-chained)
- **Tenant Isolation:** Per-tenant data separation
- **GDPR Compliance:** Data export, deletion, consent
- **Encryption:** Data at rest + in transit

---

## 📚 API Reference

[List all endpoints, methods, parameters, response formats]

---

## 🛠️ Examples

### Example 1: Basic usage
[Full code example]

### Example 2: Advanced usage
[Full code example]

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

---

## 📄 License

Apache 2.0. See [LICENSE](../../LICENSE).

---

## 🙋 Support

- **Issues:** [GitHub Issues](https://github.com/CorvinLabs/Corvin-Marketplace/issues)
- **Discussions:** [Marketplace Discussions](https://github.com/CorvinLabs/Corvin-Marketplace/discussions)
- **Security:** security@corvinlabs.io

---

**Version:** X.Y.Z | **Status:** Production | **Last Updated:** YYYY-MM-DD
```

---

### Content Guidelines

**Style:**
- Clear, non-technical audience (operators, not just engineers)
- Action-oriented language ("Create", "Configure", "Deploy")
- Concrete examples over abstract descriptions
- Visual diagrams for complex concepts

**Required Sections:**
- Hero section (title + tagline)
- "What it does" (problem + solution)
- Key features (bulleted, 3–5 items)
- "How it works" (architecture + flow)
- Quick start (installation + basic usage)
- Specifications (performance, limits, compatibility)
- Security & compliance notes
- Complete API reference (if applicable)
- Practical examples (≥2, runnable code)
- Contributing guidelines
- Support contact info

**Tone Examples:**

✅ **Good:** "The Workflows Plugin transforms your business processes into automated, self-healing pipelines. Define once, execute reliably across your entire platform."

❌ **Bad:** "This plugin implements workflow execution logic using DAG-based task orchestration with cron scheduling."

---

### 2. SVG Diagrams

**Location:** `plugins/buildin/<category>/<name>/docs/assets/`

**Required Diagrams:**

| Diagram | Purpose | Audience |
|---------|---------|----------|
| **architecture.svg** | Component overview + data flow | Technical leads |
| **workflow.svg** (or **flow.svg**) | Typical user workflow / execution sequence | All users |
| **feature-matrix.svg** (optional) | Visual breakdown of features by tier/capability | Product managers |

**Diagram Standards:**

- **Dimensions:** SVG viewBox="0 0 1000 800" (landscape, 1000×800 minimum)
- **Colors:** Use brand-neutral palette (blues, greens, oranges for different layers)
- **Labeling:** Every component must be labeled; use arrows to show data flow
- **Professional:** Clean lines, consistent sizing, readable fonts (min 10pt)
- **Accessibility:** Descriptions in alt text or title attributes
- **No raster:** Pure SVG, no embedded PNGs/JPGs

**Tools to Create Diagrams:**
- Draw.io (free, exports to SVG)
- Miro (collaborative, SVG export)
- Adobe Illustrator
- Manual SVG (for simple diagrams)

---

### 3. Quality Standards

| Aspect | Standard |
|--------|----------|
| **README.md word count** | ≥1,000 words (comprehensive) |
| **Examples** | ≥2 runnable code examples |
| **API documentation** | Every endpoint/method documented |
| **Diagrams** | ≥2 SVG diagrams (architecture + flow) |
| **Security section** | Mandatory; covers audit, encryption, compliance |
| **Readability** | Clear for non-technical operators |
| **Accuracy** | Matches actual plugin behavior (no outdated info) |
| **Freshness** | Last updated date shown; refresh annually |

---

## Enforcement

### 1. Marketplace Index Validation

The marketplace registry scans each plugin for:
- ✅ README.md exists
- ✅ README.md > 500 words
- ✅ `docs/assets/` directory exists
- ✅ ≥1 SVG diagram present
- ✅ API reference section exists (if applicable)

**Status:** `documented` (TRUE/FALSE) in plugin index JSON.

### 2. CI/CD Gate

Every PR adding or updating a plugin must pass:

```bash
# Validation script (runs in CI)
scripts/validate_plugin_docs.sh

# Checks:
# - README.md exists and is readable
# - Word count ≥ threshold
# - All SVG diagrams in `docs/assets/`
# - No dead links in README
# - YAML frontmatter if applicable
```

Exit codes:
- `0` → Documentation valid
- `1` → Documentation missing or invalid (PR blocked)

### 3. Code Review Checklist

Reviewer must verify:

```markdown
- [ ] README.md is comprehensive (≥1,000 words)
- [ ] Examples are runnable and match plugin behavior
- [ ] Architecture diagram is clear and labeled
- [ ] Workflow/flow diagram explains typical usage
- [ ] Security section covers audit, encryption, compliance
- [ ] API reference is complete (all endpoints documented)
- [ ] Last updated date is current
- [ ] No dead links or missing assets
- [ ] Professional formatting (consistent headings, code blocks)
```

Failure to pass checklist → PR review blocked until addressed.

---

## Migration Path

### For Existing Plugins (2026-09-23+)

**Timeline:**
- Week 1 (Sep 23–29): Draft README.md + diagrams
- Week 2 (Sep 30–Oct 6): Review + iterate
- Week 3 (Oct 7–13): Merge + publish

**Process:**
1. Run audit script to identify documentation gaps
   ```bash
   python3 scripts/plugin_docs_generator.py --audit
   ```

2. For each plugin missing docs:
   - Create branch: `docs/plugin-<name>-documentation`
   - Add README.md using template
   - Create diagrams in `docs/assets/`
   - Submit PR with documentation improvements

3. Merge once code review passes

### For New Plugins (2026-09-23+)

**Requirement:** Documentation MUST be included in the PR. No exceptions.

**Process:**
1. Developer includes README.md + diagrams in initial PR
2. Code review gates: documentation must pass validation before merge
3. Merged plugin is immediately discoverable and usable

---

## Template & Tools

### README.md Template

See: `plugins/buildin/orchestration/workflows/README.md` (example)

Copy this template for new plugins:
```bash
cp plugins/buildin/orchestration/workflows/README.md \
   plugins/buildin/<category>/<name>/README.md
# Edit to match your plugin
```

### SVG Diagram Templates

Diagrams in `/docs/assets/`:
- `architecture.svg` — Copy + edit for your plugin
- `workflow.svg` — Copy + edit for your plugin

### Generator Script

Auto-scan and report gaps:
```bash
python3 scripts/plugin_docs_generator.py --audit
python3 scripts/plugin_docs_generator.py --generate-template <plugin-name>
```

---

## Examples of Compliant Plugins

- **Workflows Plugin** (`plugins/buildin/orchestration/workflows/`)
  - README.md: 2,500+ words
  - Diagrams: architecture.svg, workflow-execution-flow.svg
  - Examples: 3 runnable workflows
  - API: 8 endpoints fully documented

- **Video Producer** (forthcoming)
- **Knowledge Graph** (forthcoming)

---

## Exceptions & Waivers

### When Documentation MAY be Lighter

**Internal plugins** (not in marketplace):
- No marketing README required
- Docstrings + code comments sufficient

**Experimental plugins** (flag: `status: experimental`):
- Lighter documentation acceptable
- Must still have: architecture diagram + quick start

### Exception Request Process

1. File issue: `[docs-exception] Plugin Name`
2. Justify: Why lighter docs are acceptable
3. Maintainer approval required

---

## Questions & Support

- **Documentation questions:** File issue `[docs-standard]`
- **Template help:** See `PLUGIN_DOCUMENTATION_STANDARD.md` (this file)
- **Tool support:** See tool vendors (Draw.io, etc.)

---

**Last Updated:** 2026-09-23  
**Maintained By:** Marketplace Governance Team  
**Status:** ACTIVE & ENFORCED
