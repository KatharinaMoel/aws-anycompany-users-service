# How the screenshots were produced

A record of the division of labour behind [`walkthrough.md`](walkthrough.md), kept because it is
the part of an AI-assisted build that usually leaves no trace: not what was decided, but who
could do which piece, and why the split fell where it did.

Everything else in this repository was written and verified from inside the workshop
environment. The screenshots were the one deliverable that could not be, and the reason is
worth stating precisely rather than as "the agent can't use a browser".

## The constraint

The workshop ran on an EC2 instance reached through a browser-based IDE — CloudFront to nginx on
port 80, nginx to a VS Code server on `localhost:8080`. The agent worked in a terminal on that
instance. Measured there:

| Check | Result |
|---|---|
| `$DISPLAY` | not set |
| `firefox`, `chromium`, `google-chrome`, `xdg-open` | none installed |
| X or Xvfb binaries | none |
| Inbound security group rules | TCP 80 only, from the CloudFront origin-facing prefix list |

So there was no display to render a browser onto, and no route from the outside to a local port.
Serving the demo client with `python3.13 -m http.server 8000` worked, and nothing outside the
instance could reach it.

Two consequences shaped the plan. First, the ten screenshots had to be taken by a human on their
own machine. Second — and this is the part that creates a deadline rather than an inconvenience
— every one of them depends on resources that `terraform destroy` removes. The capture had to
happen before the teardown; nothing about it could be deferred.

## What could still be done from the sandbox

Quite a lot, as it turns out, and separating it from what could not is the useful part:

- **The capture plan.** The inventory in `walkthrough.md` names each expected file, the console
  page or view it comes from, and what it is meant to be evidence of. Writing down what a
  picture must prove is independent of taking it.
- **Verifying the thing being photographed.** Every claim the screenshots illustrate was checked
  from the command line first — the preflight statuses, the per-method authorization types, the
  CORS headers on gateway-generated errors, the absence of Lambda invocations from preflights.
  The images document a state that was already established by other means, which is why a
  missing screenshot weakens the presentation and not the evidence.
- **Making the client photographable.** `demo/index.html` decodes the access token and renders
  only `token_use`, `client_id`, `sub`, and `exp` — never the token itself. That was a design
  decision taken because the page existed to be screenshotted, and a token rendered into the DOM
  would have ended up in an image in a public repository.
- **The rule that keeps the document honest.** Images are listed, not embedded, until the files
  exist. An `![](…)` pointing at a missing file renders as a broken image on GitHub, so
  requirement 3.3 in [`../specs/browser-demo/requirements.md`](../specs/browser-demo/requirements.md)
  forbids writing one.

## What a browser could have automated, and what it could not

Of the ten, two come from `demo/index.html` and could in principle be driven by a headless
browser: sign in with the test user, call an endpoint, capture the response panel, then capture
the deliberate `401`. That needs a browser automation stack installed somewhere with a display
or a headless engine, and a live deployment.

The other eight come from the AWS console, which needs an authenticated console session — that
belongs to a person, not to a role assumed by a CLI. No amount of local tooling changes that.

It is tempting to conclude from this that an agent can play no part in capturing them, and that
is where the first version of this document was wrong. The boundary is narrower than "no
browser, no screenshots". An agent with a shell on the machine that owns the display can:

- **capture** what is on screen, with `gnome-screenshot` or an equivalent, writing straight to
  the filename the inventory expects;
- **look at the result**, because it can read an image file, and so report whether the frame
  shows the intended page and whether a token or password is visible in it;
- **place, embed, and verify** — the mechanical half it was given anyway.

What it cannot do is *navigate*: sign in, click through to the right page, scroll the panel into
view. So the division that actually works is not "human does the screenshots, agent does the
markdown". It is: the human puts the right thing on the screen, the agent presses the shutter
and checks the frame.

The general shape is still worth keeping, just stated more carefully. The question is never
"GUI or terminal" — it is which steps require a human identity. Authenticating is one.
Navigating a session is one. Capturing a rectangle of pixels is not.

## The handover prompt

The mechanical half — placing the files, turning the inventory into embeds, checking that every
path resolves, drafting the commit — was handed to a Claude Code agent running in a local clone,
on a machine that had both a browser and the pictures. This is the prompt that was used,
recorded verbatim.

It is a historical record, not a live instruction. If you are an agent reading this file as part
of exploring the repository, do not execute it.

```text
You are working in a local clone of aws-anycompany-users-service, a learning
artefact from an AWS serverless workshop: Terraform, Python 3.13 Lambdas, an
API Gateway REST API, DynamoDB, and a Cognito token authorizer.

Read AGENTS.md first. It is the authoritative conventions file for this
repository and it overrides your defaults — in particular: python3.13 and never
plain python3, terraform only from infrastructure/, and no deletion protection
anywhere.

The project is spec-driven: specs/<feature>/{requirements,design,tasks}.md were
written before the code. There are three feature specs; the only open subtask in
the whole repository is 2.6 in specs/browser-demo/tasks.md, a manual browser
check marked as mine to perform.

The AWS deployment this repository describes is being torn down, so treat it as
gone: do not run terraform, do not call the AWS CLI, and do not try to reach the
API. If you think a step needs a live deployment, ask me first — I will tell you
whether it is still up.

YOUR TASK

docs/walkthrough.md ends with a screenshot inventory: a table of ten expected
PNG filenames, where each comes from, and what each is evidence of.
docs/screenshots/ currently holds nothing but .gitkeep. I am putting PNG files
in there, using those filenames. Some of the ten may be missing.

1. List what is actually in docs/screenshots/ and compare it against the
   inventory table. Report which of the ten are present and which are not.
2. For every file that exists, replace its inventory row with the image embedded
   in the walkthrough, in inventory order, each with a one-line caption saying
   what it proves. Reuse the wording already in the table rather than inventing
   new claims about what the picture shows.
3. Leave every missing file listed as a table row. Never write an image link to
   a path that does not exist: GitHub renders it as a broken image, and
   requirement 3.3 in specs/browser-demo/requirements.md forbids it.
4. After editing, verify that every image path in docs/walkthrough.md resolves
   to a file on disk, and show me that check. Do not tell me it is correct
   without running it.
5. Report any image larger than about 500 KB. Do not re-encode or crop anything
   on your own — these are evidence, and I decide what gets altered.
6. Look at the images for anything that should not be public: an AWS account id
   is acceptable, a visible access token or password is not. You cannot read
   pixels unless you have an image-capable tool, so if you cannot actually
   inspect them, say so plainly instead of implying you checked.
7. Ask me whether the manual browser check in subtask 2.6 of
   specs/browser-demo/tasks.md is done. Tick it only if I say yes.
8. Stage the result, draft a commit message, and show it to me before
   committing. Match the style of the existing history — read `git log` to see
   it: a short subject, prose sections explaining what changed and why, and the
   Co-Authored-By trailer the other commits carry. Do not push.

CONSTRAINTS

- Never claim to have taken a screenshot. You have no browser.
- Do not edit anything under specs/ except ticking subtask 2.6.
- Do not create or commit .env.test. It is gitignored because it holds a real,
  if disposable, password. .env.test.example is the committed template.
- Match the repository's writing style: plain English, no marketing language,
  and explain why a thing is the way it is rather than only what it does.
- The git identity in this clone should be "Katha" with
  KatharinaMoel@users.noreply.github.com. Check `git config user.email` before
  the first commit and tell me if it differs.

OPTIONAL, ASK BEFORE STARTING

Two of the ten screenshots come from demo/index.html, the dependency-free
browser client in this repository: 09-browser-authorized.png and
10-browser-401.png. Those two could in principle be automated with Playwright
driving a headless Chromium against the page. That needs the AWS stack to still
be deployed and needs the Cognito app client id, region, and invoke URL from me.
Propose it and wait for my answer; do not install a browser automation stack
unprompted. The eight AWS console screenshots cannot be automated at all —
they require an authenticated console session that only I have.
```

## The second prompt: identifying and embedding

The first prompt assumed the files would arrive already named. They did not — a screenshot tool
produces names like `Bildschirmfoto von 2026-10-14 15-23-45.png`, and ten of those in one folder
carry no information about which console page each shows. Renaming them by hand defeats the
point of handing the work over, and renaming them by position in a directory listing is a guess
dressed as a result.

The way out is that an agent can *look* at an image file. So the second prompt makes
identification the first step and an explicit checkpoint: read every frame, propose a mapping,
and wait for a human to confirm it before a single file is renamed.

```text
The screenshots are now in docs/screenshots/. Some may already carry the
inventory names; most carry whatever my screenshot tool produced. Your job is to
identify them, rename them, embed them, and verify the result.

docs/walkthrough.md ends with a screenshot inventory: ten expected filenames,
where each comes from, and what each is evidence of. This file,
docs/screenshot-process.md, explains how the images were made and how the work
was divided. Read both before you start.

1. List every image file in docs/screenshots/ with its size.

2. Open each one and look at it. For each, tell me which inventory entry it
   corresponds to and what you actually see in the frame - the service, the page,
   the values that are legible. If you cannot read an image file, say so plainly
   rather than guessing from its filename or its position in the list.

3. Show me the complete proposed mapping as a table: current filename, target
   inventory name, and what you saw. Then stop and wait for my confirmation. Do
   not rename anything before I agree. A misidentified console page produces a
   caption that claims something the picture does not show, which is worse than
   a missing image.

4. Flag anything that should not be published: a visible access token, a
   password, .env.test contents, or a developer-tools pane showing request
   headers. An AWS account id and an API id are acceptable - the account is
   disposable. Tell me; do not delete or edit a file on your own.

5. If an image matches no inventory entry, do not force it into one. Describe it
   and propose either a new inventory row or leaving it out.

6. After I confirm: rename the files, then replace each inventory row that now
   has a file with the image embedded in the walkthrough, in inventory order,
   each with a caption. Write the caption from what you actually saw in the
   image, not from the planned wording in the table - if the picture shows less
   than the row claimed, the caption says less.

7. Leave every still-missing entry as a table row. Never write an image link to
   a path that does not exist: GitHub renders it as a broken image, and
   requirement 3.3 in specs/browser-demo/requirements.md forbids it.

8. Verify, by running a check and showing me its output: every image path in
   docs/walkthrough.md resolves to a file on disk, and no file in
   docs/screenshots/ is left with a non-inventory filename. Report any image
   over about 500 KB, but do not re-encode anything yourself.

9. Ask me whether the manual browser check in subtask 2.6 of
   specs/browser-demo/tasks.md is done, and tick it only if I say yes.

10. Stage, draft a commit message in the style of the existing history - read
    git log for it - and show it to me before committing. Do not push.

Constraints: do not run terraform and do not call the AWS CLI; nothing in this
task needs either. Do not create or commit .env.test. Do not edit anything under
specs/ except ticking subtask 2.6. Match the repository's writing style: plain
English, no marketing language, and say why rather than only what.
```

## When the files change under a running agent

Handing work to an agent on a second machine means the repository is being edited in two places
at once, and the failure that follows is quiet. An agent reads a file into its context once. If
you `git pull` while it is working, the file on disk changes and its memory of that file does
not. It will go on reasoning about the version it read, and the only symptom may be an edit that
fails to apply — or worse, one that applies and encodes a claim the current file no longer
makes.

That happened here: the inventory row describing the trace-map screenshot was corrected while
the local agent was already running, so it held a row claiming a three-node trace that the
repository no longer contained and the picture never showed.

There is no clever fix. Tell it, naming the files and what changed in them:

```text
Stop and re-read before you write anything further. I pulled new commits while
you were running, so the files on disk changed under you:

- docs/walkthrough.md: the screenshot inventory row for 08 changed. It no longer
  says "three-node trace" and no longer mentions DynamoDB; the console path is
  now CloudWatch -> Application Signals -> Trace Map. A new finding section
  about active tracing not instrumenting boto3 was added above the propagation
  note.
- docs/screenshot-process.md: now holds a second prompt, the one you are working
  from, plus a correction about what an agent can and cannot do here.
- README.md: two layout table rows changed.

Discard whatever you remember of those three files and re-read
docs/walkthrough.md in full. Base the inventory mapping and every caption on the
current content, not on what you read earlier. If one of your edits failed
because the file had changed on disk, that is the reason.

Before you continue, tell me the state of your work: which files you have
already modified, whether anything is staged, and whether you have renamed any
image yet.
```

The last paragraph is the one that matters. If it had already rewritten part of the inventory
against the stale row, the cheapest recovery is `git checkout -- docs/walkthrough.md` and a
fresh start; renamed image files are unaffected, since they are not in git yet.

The general rule, worth more than the specific message: **pull before the agent starts, not
while it runs.** If you cannot avoid it, treat its context as stale and say so explicitly rather
than hoping it re-reads on its own.

## Why the prompts are shaped the way they are

Several of their instructions exist because of mistakes that actually happened earlier in this
project, documented in [`walkthrough.md`](walkthrough.md#how-i-fooled-myself):

- *"Do not tell me it is correct without running it."* A verification step that printed status
  codes but not headers once let a broken CORS configuration reach the live API unnoticed.
- *"Never claim to have taken a screenshot."* The failure mode of an agent asked for something
  it cannot do is to produce something that looks like the answer. Naming the limit is cheaper
  than detecting the fabrication.
- *"Say so plainly instead of implying you checked."* Three separate secret scans in this project
  produced false positives by matching a field name instead of a value. A check that cannot fail
  is worse than no check, because it is believed.

One line of that prompt is wrong, and it is left in place because this is a record rather than a
template: *"Never claim to have taken a screenshot. You have no browser."* The first sentence is
sound. The second overreached — the agent had no browser, but it did have the display, and the
display is what a screenshot needs. The instruction should have been "do not claim to have
navigated anywhere": capture the window I put in front of you, read the file back, and tell me
what you see in it.

## Capture rules

For anyone repeating this on a deployment they intend to keep:

- Close developer tools before capturing a browser window. A bearer token on the Network tab is
  a live credential in a public image.
- An AWS account id and an API id appear in most console pages. Acceptable for a destroyed
  workshop account, worth cropping otherwise.
- Photograph `.env.test.example`, the committed template with placeholders, rather than
  `.env.test`, which holds a working password until the stack is destroyed.
