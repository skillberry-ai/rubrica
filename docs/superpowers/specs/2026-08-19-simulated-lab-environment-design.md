# Simulated lab environment — design

Date: 2026-08-19
Status: proposed

## The problem

A suite that runs is not the same as a suite that runs *somewhere*. Today
`emit` writes a Harbor task package whose `task.toml` declares

```toml
[environment]
docker_image = "registry.access.redhat.com/ubi9/ubi:latest"
mcp_servers = [{ name = "backend", url = "${BACKEND_MCP_URL}" }]
```

Nothing supplies `BACKEND_MCP_URL`, nothing runs a backend, and Harbor never
expands the placeholder — `resolve_env_vars` is applied to `env` dicts only,
never to `mcp_servers[].url`, so the literal string `${BACKEND_MCP_URL}`
reaches the agent's MCP config. The suite is emittable and unrunnable.

The gap is a lab: an environment where the agent under test exercises its real
tools against a world we control, so a scenario's expected trajectory can
actually be observed.

`simulation-harness` is that world. It takes one OpenAPI specification, derives
a state schema and behavioural skill from it, and serves the result as an MCP
server — one tool per operation, responses generated against a persisted,
schema-validated store. Data is authoritative; only behaviour is
model-mediated.

This design connects the two, as two enhancements to Rubrica.

## Scope

In scope: discovering the agent's environment-dependent tools, describing them
as OpenAPI, generating simulations for the ones a human selects, translating a
scenario's seed into per-service simulator databases, and standing the whole
thing up under Harbor during `smoke`.

Out of scope: optimizer integration; anything about how the emitted feedback is
consumed downstream; changes to `simulation-harness` itself.

## What the simulation harness constrains

Four properties of the harness shape everything below. All four are verified in
its source, not inferred from documentation.

**MCP only.** No REST routes are mounted for simulated operations
(`rg add_api_route` over its source returns nothing). The only HTTP surface is
the control plane under `/api/v1` and the MCP transports. A simulated tool is
therefore reachable *as an MCP tool* and no other way.

**The service is the unit.** One spec → one skill → one simulation, at most one
active simulation per process (a second create returns 409). Tools belonging to
one backend must be described by one spec, or they get disjoint databases and
an entity created through one tool is invisible to another.

**Tool names are derived from the spec.** `sanitize_operation_id(raw, *,
method, path)` takes `operationId` verbatim — sanitised to
`^[a-zA-Z0-9_-]{1,64}$` — and falls back to `{method}/{path}` when absent. The
name the agent sees is a function of the spec we synthesise.

**Generation and serving are already separate.** `setup_simulation` generates
and rests at `generated`; `start_simulation(name=...)` starts "from baked
artifacts. No generation."; `startup.autostart_enabled` +
`autostart_simulation` let a container boot straight into serving a named
skill. Generate once, serve many.

## Enhancement 1 — interfaces in the world model

### Tools, grouped into services

The unit of analysis is a tool the agent registers, and the unit of simulation
is the service those tools belong to. Extraction gains a new claim subject: the
tools the target declares, and their grouping into services.

Grouping is a judgment with evidence, not a string match — two tools share a
service when they address the same backend, and the evidence is a shared base
URL, a shared client construction, a shared credential, or a shared MCP server
entry. The grouping determines how many simulators exist, so it is reviewable.

### Containment as signals, not a verdict

Whether a tool reaches outside the process is sometimes obvious (a configured
remote MCP server) and sometimes not (a helper three calls deep that lazily
constructs an HTTP client). Rubrica does not compute a `contained: true|false`
field, because that is the one place the pipeline would assert a certainty it
cannot support.

Instead each service carries **signals**, each with an evidence locator:

- a remote MCP server is configured for these tools
- an HTTP client or SDK is constructed in the implementation
- a credential or base-URL environment variable is read
- a network-capable dependency is imported
- no outward-facing evidence was found in the artifacts that were read

The last is deliberately phrased as absence of evidence rather than evidence of
absence. A tool that looks self-contained but holds a hidden call produces a
suite that passes in the lab and fails in production; that asymmetry means
uncertainty must not read as "contained".

### Specifications synthesised backwards from the tool contract

For each service, a new stage writes one OpenAPI document. It runs before Gate
1 so the human reviews specifications rather than service names — a selection
decision is not meaningful without seeing what would be simulated.

Synthesis runs **backwards from the tool contract**. The agent already declares
each tool's name and input schema; the substitution downstream is invisible to
the agent's reasoning only if that contract is preserved byte for byte.
Therefore `operationId` is set to the agent's own tool name, and the request
body is its input schema. Path and method are carriers, chosen deterministically
so a name survives sanitisation unchanged.

### Response schemas, inferred from trajectories

Tools are typically registered with a name, a description, and an input schema —
no output schema. That absence is not a fidelity detail. In the harness,
response schemas feed generation at two load-bearing points: the operations
stage `$ref`-resolves `get_success_response_schema()` into its prompt, and the
analyze stage derives **entities** from response shapes, with the merged
entity's `required` set taken from the response schema. Generation fails outright
when no entity can be derived.

So a spec without `responses` risks not generating at all, and where it does,
the state store's shape is inferred from inputs rather than from what the tool
returns. Where trajectories are available they are the only artifact revealing
response shape, and inferring `responses` from observed tool results is close to
a precondition for a useful simulation.

Inference generalises from instances. A field present in every observed call
looks required; unions flatten; rare shapes are invisible. Each inferred
response schema therefore records its observation count and the trajectories it
came from, so Gate 1 can distinguish "inferred from 2 observations" from
"inferred from 40". Specifications assembled from a declared contract are
`stated`; those carrying inferred responses are `reverse_engineered`.

### Gate 1 approves a selection

The gate brief gains a section per service: its tools, its signals with
locators, its synthesised specification, and the provenance of each response
schema. The human marks which services to simulate. **The default is none** —
simulation is opt-in, and a run that selects nothing behaves exactly as it does
today.

The decision is recorded through `rubrica decide` with the human's reason,
because the deciding factors are frequently not in the artifacts at all: an API
is rate-limited, a staging environment is unreliable, production is off limits.

Services that are neither simulated nor available in the lab make every
capability that touches them unreachable. That is a coverage constraint, not a
filter: it belongs in the world model's `denominator` so the coverage matrix
does not report holes the run can never fill.

## Enhancement 2 — from selection to a running lab

### Generate simulations between Gate 2 and Gate 3

Gate 2 is the cost gate; everything below it is paid per scenario. Simulation
generation is paid per *service*, a different axis, and it runs after Gate 2 so
a rejected scenario set does not leave generated simulations nobody needs.

The stage starts **one** harness instance, calls setup once per selected
service, retrieves each bundle — `SKILL.md`, `schema.json`, `db.json`,
`api.json` — and shuts the instance down. The bundles become run artifacts.
Each service's derived `schema.json` is the schema its database must satisfy;
the harness owns its own state shape, and Rubrica consumes it. There is no
reconciliation step and no rejected write, because nothing writes a database
the harness did not describe.

### Translate one seed into many databases

A scenario's seed describes one world. Each simulated service needs its own
database conforming to its own derived schema. Translation is a compiler stage,
not a mapping: the world model is the source and the per-service databases are
projections of it.

Projection carries an obligation. An entity exposed by two services must appear
identically in both, or the agent sees a reservation through one tool and not
another. This is a cross-artifact consistency property, which is what the
reference-checking layer exists for, so it becomes a new check: every entity the
expected trajectory touches is present, and identical, in every simulated
service that exposes it.

### Emit a package that can stand itself up

`emit` gains, per task:

- one `mcp_servers` entry per simulated service, with an explicit `transport`
  (the field defaults to `sse`, while the harness fixes its transport at
  startup — a silent mismatch is a silent failure) and a URL that is a compose
  service name, not an unexpanded placeholder
- a `docker-compose.yaml` adding one harness service per simulated service
  beside Harbor's own `main`
- the per-service database payloads
- `schema_version` raised from `1.3` to `1.4`

### Smoke stands up the lab

For each task, `smoke` brings up one harness container per simulated service,
each autostarting from its baked bundle — no generation at run time. Each
container's database is seeded from the task's payload for that service. The
agent under test is then wired to the simulators **at the point where it
registers its tools**: the tool's transport is redirected to the simulated MCP
endpoint while its name and input schema stay identical.

One simulator per service per task also sidesteps the one-simulation-per-process
limit: parallel trials get their own containers rather than contending for a
single session.

`golden.json` deliberately carries no tool results — the seed is the source of
truth for results. That holds precisely as long as the simulator is seeded from
the same seed the oracle was derived from. Skip the seeding step and the two
worlds diverge silently, which is why seeding is part of bringing the
environment up and not a separate operator action.

## Risks

**Source-derived claims are unexercised.** `source_code` is a declared input
kind, and no run has filed a claim from a source file. Both containment signals
and tool discovery lean on exactly that path. The mitigation is to start with
targets whose tools are declared (MCP tool schemas, specifications) and treat
source-derived signals as the harder second case rather than the first.

**A wrong specification fails silently downstream.** The harness will generate a
coherent simulation of the wrong API, and the suite will test the agent against
a world that does not match production. Nothing in the run detects this; only
Gate 1 review does. This argues for showing provenance and observation counts
prominently in the brief.

**One instance, sequential generation, is slow for many services.** Acceptable
at the scale this design targets, and the constraint is the harness's, not ours.

## Open questions

- How a service's tools are grouped when the only evidence is a shared
  credential — is that sufficient, or does it need a shared base URL?
- Whether path and method assignment should be derived from the tool name or
  fixed by convention, given that only `operationId` is contractually
  significant.
- Whether an agent whose tools are not MCP-native is out of scope permanently
  or wants a translation shim later.
- Whether Harbor should be asked to expand `${VAR}` in `mcp_servers[].url`
  upstream, which would make the placeholder approach viable as an alternative
  to compose service names.
