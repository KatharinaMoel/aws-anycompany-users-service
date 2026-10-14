# How this was built

A record of the process, written at the end of the session that produced it. The
[walkthrough](walkthrough.md) covers what was built and what went wrong technically; this file
covers how the work was organised, and where the method failed rather than the code.

It exists because the process was the point. The AWS resources were disposable from the first
line of Terraform; practising spec-driven development with an agent was not.

## The loop

Every one of the three features followed the same four steps, in order, with the next step
refusing to start until the previous one was reviewed:

1. **`requirements.md`** — user stories with acceptance criteria in two fixed forms:
   `WHEN <trigger>, THE <actor> SHALL …` for event-driven behaviour, and `THE <actor> SHALL …`
   for an invariant. Criteria are numbered, because later steps cite them.
2. **`design.md`** — the architecture, the decisions, and crucially the *rejected* options with
   the reason. Most of what is worth reading in this repository ended up here.
3. **`tasks.md`** — task groups of three to six checkboxes each, every group ending in a
   verification step, every infrastructure group ending in `terraform apply` plus a check
   against the deployed resource. Verification steps name the criteria they prove, as
   `(verifies 1.5)`.
4. **Implementation**, one task group at a time, ticking each checkbox as it completed and
   stopping for approval between groups.

The ordering constraint did real work. Writing the criteria first forced questions that are
easy to defer — what does search return when nothing matches, is the match case-sensitive,
what happens to unexpected fields in a request body — and each answer became a test rather
than a discovery during review.

Citing criterion numbers in verification steps did the second half of that work. It makes an
untested criterion visible: if no task names it, nothing proves it.

## One file holds the conventions

`AGENTS.md` in the repository root is the single source for "how things are done here":
Terraform rather than SAM or CDK, `python3.13` and never plain `python3`, no hardcoded region,
`plan -out=tfplan` before every apply, no `prevent_destroy` anywhere, JSON logs with no event
dumps and no tokens, one `.tf` file per concern.

Its value is not that it is long — it is short — but that it removed a whole class of
back-and-forth. Nothing in the three specs had to re-litigate the runtime, the region handling,
or the logging format, and a decision that contradicted the file was wrong by construction
rather than by argument.

## Verification was the default, not the last step

The working rule was: a claim about the deployed system is worth nothing until it has been
measured. In practice that meant reading back from AWS after every apply — `describe-table`,
`get-method`, `curl -i`, `logs filter-log-events`, trace documents — rather than inferring
success from a clean `terraform apply`.

This caught things that would otherwise have shipped as documentation: a GSI query denied by an
IAM policy that looked complete, CORS gateway responses silently wiped by an OpenAPI import,
an authorizer refetching the JWKS on every invocation, and a trace map that shows two services
where the documentation claimed three. All of them are in the
[walkthrough](walkthrough.md#what-went-wrong-and-why).

It also produced the opposite lesson, four times over: the measurement itself can be the thing
that is broken. A CloudWatch filter pattern that matched a field name reported a catastrophic
token leak that did not exist; a shell default of `${4:-$TOK}` instead of `${4-$TOK}` made the
"request without a token is rejected" check send a token and pass; a secret scan flagged three
files whose only sin was containing the string `AWS_SECRET_ACCESS_KEY`. A check that cannot
fail is worse than no check, because it is believed.

## Where the method failed

Three failures were mine as the agent, and they share a shape worth naming.

**Reasoning from documentation instead of from the system.** Asked whether a `type: "agent"`
hook works on the `Stop` event, I said no, citing a reference that lists only tool events. The
user's hook was already firing. The documentation was a weaker source of truth than the
running system, and I had the running system available.

**Over-generalising a limitation.** Told that the workshop sandbox had no browser, I concluded
the screenshots could not be automated at all — and repeated it in a committed document. The
correct boundary is narrower: an agent with a shell on the machine that owns the display can
capture a window and read the image back; what it cannot do is navigate an authenticated
session. The distinction is not GUI versus terminal, it is which steps need a human identity.
That document now carries the correction and the original claim, because a record that quietly
fixes itself teaches nothing.

**Breaking a running agent's assumptions.** Work was handed to a second Claude Code session on
the user's own machine, and the repository was edited here while that session was running. An
agent reads a file into context once; a `git pull` under its feet changes the file and not its
memory of it. See [the note on that](screenshot-process.md#when-the-files-change-under-a-running-agent).

## The tooling that helped

- **Plan mode** for the first task group. Writing out the provider configuration, the expected
  `plan` summary, and the exact `describe-table` check *before* touching AWS turned the first
  apply into a confirmation rather than an experiment.
- **A skill**, `.claude/skills/test/SKILL.md`, holding the project's test instruction: run the
  suite, and when a test fails decide from the specs whether the code or the test is wrong —
  and if the test is wrong, stop and explain before changing it, because each test encodes an
  acceptance criterion. Four words of policy that prevent the obvious failure mode.
- **A `Stop` hook** that reviews the README against the repository after every turn. Its record
  over this session: one genuine catch (a spec directory missing from the layout table), one
  reasonable nudge (a singular that should have been a plural), and two false positives — it
  once compared test *cases* against test *functions* and reported the README as overstating
  the suite, when 84 collected cases and 52 `def test_` functions were both correct, the
  difference being six `parametrize` decorators. A reviewer with no memory of the conversation
  catches what a participant stops seeing, and invents what a participant would never ask.

## Division of labour

The agent wrote the specs, the Terraform, both Lambda functions, the tests, the end-to-end
suite, and the documentation, and verified each against live AWS. The human set the scope,
reviewed every spec before implementation, approved each task group, supplied the AWS
environment, and did the things that need a person: a browser, an authenticated console
session, a GitHub account, and the decision about what gets published.

The boundary moved once during the session and in a useful direction — see the over-generalising
failure above. It is worth probing rather than assuming.

## The shape of the result

| | |
|---|---|
| Features, specified before implementation | 3 |
| Acceptance criteria | 65 |
| Task subtasks | 85, of which 84 completed |
| Terraform files | 8, one per concern |
| Python in `src/` | 390 lines across two functions |
| Unit tests | 84 cases from 52 functions, 97% statement coverage |
| End-to-end assertions against live AWS | 43 |
| Commits | 13 |

The single open subtask is the manual browser check, which needs a person at a browser.

## What I would change

Write the end-to-end suite into the repository from the start instead of leaving it in `/tmp`
for two features, where it would have been lost with the environment. Add the X-Ray SDK to the
CRUD function if a trace that shows DynamoDB matters, rather than letting "active tracing"
imply it. And pull before an agent starts, never while it runs.
