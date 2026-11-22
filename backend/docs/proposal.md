Plan2Walk: Chat-First Floor Plan Generation and Editable 3D Walkthroughs
AI-4009 Generative AI | Assignment 3 | Project Proposal | Track: R&D Product

National University of Computer and Emerging Sciences (FAST-NUCES), Department of Computer Science

Item	Details
Product name	Plan2Walk
One-line description	An AI product that turns a user's description of a home, or an
existing 2D plan, into a validated floor plan, builds an interactive
3D walkthrough with deterministic code, and lets the user refine
the design through chat, with every AI output checked by
geometry rules
Project track	R&D Product
Research focus	Prompted vision-language models versus classical computer vision
for converting floor-plan images into valid, faithful and editable
layouts, and the effect of deterministic validate-and-repair
Group members	Hamna Asif (23i-0658), Ayesha Noor (23i-0736)
Course and supervisor	AI-4009 Generative AI; Dr. Akhtar Jamil
1. Title and Team
Plan2Walk is a web product for home builders, small contractors and homeowners who want to see a house before it is built. The user can start in two ways. In the main path the user describes the requirements in chat, for example the plot size, the number and type of rooms, rough room sizes and layout preferences, and the system generates an initial 2D floor plan. As an alternative input, the user uploads an existing plan image, and a vision-language model (VLM) reads it into the same structure. In both cases the AI produces a compact layout description, not a 3D model: deterministic code builds a wall graph from it, checks the geometry, and only then generates the 3D scene that can be walked through in the browser. The user then refines the design in chat, for example "add a window to the bedroom" or "move the kitchen door closer to the corner", and a tool-calling agent turns each request into a typed edit that code applies and re-validates. The result can be exported as glTF or shared through a Telegram bot.

The project follows the R&D Product track. The group builds and deploys the product and studies one primary research question about it (Section 13): how well a prompted VLM with deterministic validateand-repair converts floor-plan images into valid and faithful layouts compared with a classical computervision and OCR pipeline. The team has two members, Hamna Asif and Ayesha Noor. The work is prioritised: the core workflow is built and evaluated in Assignment 3 and completed in Assignment 4,

and further features are planned for later (Section 3). Roles are given in Section 12, and both members work on AI and engineering parts.

2. Problem and Motivation
People who build or buy a house usually get a 2D plan: a drawing of walls, door arcs, window symbols and small dimension labels. Reading it requires training. Many clients cannot picture room proportions, space or movement from it, and misunderstandings are often found only after construction has started, when changes are expensive. Many people also start earlier than that: they know what they need (a 10marla plot, four bedrooms, an open kitchen) but have no plan yet, and the first draft must come from a draftsman or architect. The usual remedy for both situations is a plan and a 3D render made by an architect or a visualisation studio. This costs money and takes days, and every change request repeats the cost. Small builders and individual homeowners, especially in Pakistan where plans are often drawn by a draftsman on one page, rarely pay for it.

The target users are homeowners who want to explore and adjust a design before approving it, home builders and small contractors who want to show a client a plan in 3D, and property agents who want a quick walkthrough from a plan they have been given. Architects and interior designers are secondary users who might use the system for a fast first draft.

Conventional software cannot do the first steps. Turning a requirement such as "three bedrooms and an open kitchen on a 30 by 60 ft plot" into a layout needs language understanding, and a floor plan image is unstructured: wall styles, symbols, fonts, scales and layouts differ from plan to plan, and rooms are identified by text labels, door arcs and context. Generative AI is needed to interpret both inputs and to turn free-text edit requests into valid actions. At the same time, geometry has to be exact: walls must close, rooms must not overlap or leave gaps, doors must sit on walls and dimensions must be consistent. Plan2Walk therefore uses AI only to propose a structured 2D layout and uses deterministic code to validate, calculate and build. It deliberately does not ask a model to generate 3D geometry directly, because a structured 2D layout can be checked by rules and edited reliably.

Table 1. Existing tools and the gap addressed by Plan2Walk

Existing tool or practice	What it does	Limitation for this problem
Architect or studio 3D
rendering	Produces high-
quality plans and
renders	Expensive and slow; every revision costs
again
Floor-plan design tools (for
example Planner 5D,
Floorplanner, RoomSketcher,
SketchUp)	Let users draw a plan
and view it in 3D	The user must draw or redraw the plan by
hand; no automatic reading of an existing
image; limited natural-language control
Commercial plan-to-3D
services	Convert uploaded
plans to 3D models	Typically manual or paid per plan; limited
editing; not designed for local plan styles
Classical CV and OCR pipelines
(OpenCV, Tesseract)	Detect walls and
read text in clean	Fragile on varied styles, hand-drawn lines
and noise; cannot reason about room
Existing tool or practice	What it does	Limitation for this problem
drawings	function
Research models for floor-plan
recognition and generation (for
example CubiCasa5K models,
House-GAN, HouseDiffusion)	Segment plans or
generate layouts
from constraints	Outputs are raster or unconstrained
polygons, not an editable, validated scene;
no chat editing
General chat assistants with
image input	Describe an image or
draft a layout in text	May invent rooms or dimensions; output is
not geometry-valid; cannot build or edit a
scene
Plan2Walk's contribution is the combination in one workflow: a chat-first layout generator with plan import as an alternative, schema and geometry validation, automatic 3D construction, and safe chatbased editing, with a measured comparison against classical methods. The team will re-check the current features of the products named in Table 1 before submission.

3. Product Overview and Features
Plan2Walk is a web application. A user describes a home in chat (or uploads a plan), reviews the generated or extracted 2D layout, opens the 3D walkthrough, edits by chat, and exports or shares the result. One user role is needed at this stage.

The features are prioritised. Core features form the complete workflow and are the work of this course project. Extended features are planned for after the core workflow works and are implemented only if time permits.

Table 2. Core and extended features

ID	Feature (user view)	Type
F1	The user describes requirements in chat (plot size, number and type of
rooms, approximate room sizes, layout preferences) and receives an
initial 2D floor plan; the user can ask for another option	Core
F2	The user uploads an existing floor plan image (PNG, JPG or PDF page),
gives its scale or one known dimension, and receives the same 2D layout
structure	Core
F3	The system checks the layout (closed rooms, shared walls, no overlaps or
gaps, doors and windows on walls, every room reachable), repairs small
problems automatically and reports the rest	Core
F4	The user sees the 2D layout with room names and dimensions and can
correct a room name, a door or a window manually	Core
F5	The system builds a 3D model and the user can orbit and walk through it
in the browser	Core
ID	Feature (user view)	Type
F6	The user edits by chat using a small set of reliable operations: rename a
room, add a window or door, move a door or window along its wall,
change an opening's size, delete an opening, and undo; every edit is
validated and previewed before it is committed	Core
F7	The user keeps a history of layouts and edits and can restore an earlier
version	Core
F8	The user exports the model as glTF and shares a render through a
Telegram bot	Core
X1	Resizing rooms and moving walls that are shared between rooms, with
neighbouring rooms updated consistently	Extended
X2	Automatic reading of written dimensions on an uploaded plan to set the
real-world scale	Extended
X3	Furniture placement, wall and floor textures, and lighting	Extended
X4	Voice commands	Extended
X5	Urdu and Roman Urdu requirements and commands	Extended
X6	Multi-storey designs and staircases	Extended
End-to-end workflow (diagram below). The user either describes the home in chat or uploads a plan. For a chat description, the language model proposes a compact 2D layout specification (rooms as rectangles on a grid, with types, sizes and adjacencies); for an uploaded plan, the VLM proposes the same specification from the image. Code builds the wall graph from the specification and validates it. If checks fail, the specific errors are sent back to the model once, and anything still failing is flagged for the user. The user reviews the 2D layout. The scene builder then generates the 3D walkthrough. The user edits by chat: the agent calls typed tools, code applies each edit to the wall graph and re-validates it, and the user approves it before it is stored as a new version. Finally the user exports or shares the result.

Chat or upload in, one validated layout out; Al proposes, code checks
errors go back once, then are flagged
Describe needs LLM proposes 2D Code builds Validate and
in chat layout spec wall graph repair geometry
Or upload an VLM reads plan
existing plan into layout spec
User reviews Build 3D scene Chat edit: agent Validate edit
2D layout and walkthrough calls typed tool and preview
User approves Store version Export gITF
the edit for undo or Telegram
O Alproposes Deterministic code O Person decides

end-to-end workflow
Both inputs feed one validated layout. AI steps only propose; code steps validate and build, and the person confirms the layout and every edit.

4. System Components and Architecture
Plan2Walk is organised in layers (architecture diagram below). The stack is kept deliberately small for a two-member team.

Frontend. A Next.js web app with a chat panel and upload, a 2D layout view, and a Three.js 3D viewer with orbit and first-person walk modes.

Backend. A FastAPI service for sessions, job management, layout storage and the chat endpoint. Long AI jobs run as background tasks.

AI layer. (a) A layout generator that turns a requirement description into a layout specification; (b) a plan-reading VLM that turns an image into the same specification; (c) an edit agent that selects and calls typed tools; (d) Pydantic validation with one retry on every output. The first version uses API models; a small open VLM is an optional comparison.

Deterministic services. Wall-graph builder, geometry validator and repair rules, scale and unit conversion, the 3D scene builder, edit tool implementations and glTF export.

Database. SQLite for layouts, versions and edit history; file storage for uploaded images and exports.

Integration. A Telegram bot that sends the render and the glTF file.

Observability. Structured logs of every model call with latency and cost.

The Al layer proposes layouts; deterministic services do the geometry
Frontend (Next.js)
Chat panel and upload 2D layout view Three,js 3D viewer
Backend (FastAPI)
API and sessions Background jobs SQLite: layouts, versions
Allayer
Layout generator Plan-reading VLM Edit agent Output validation
Deterministic services
Wall-graph builder Geometry validator 3D scene builder Edit tool engine
External services
‘APILLM and VLM Open VLM (optional) Telegram and email

system architecture

The central design rule is that AI proposes structured facts and only deterministic code does geometry, dimensions and the 3D build.

Table 3. Allocation of responsibilities between AI and deterministic code

Responsibility	AI component	Deterministic code
Understanding
requirements	LLM extracts rooms, sizes,
adjacencies and preferences from
the chat	Parsing units (ft, m, marla), checking
required fields, asking for missing ones
Proposing a
layout	LLM proposes room rectangles
on a grid inside the plot	Snapping to the grid, building shared walls,
junctions and openings
Reading an
uploaded plan	VLM identifies rooms, labels,
walls, doors and windows	Image resizing, contrast normalisation, OCR
text hints, file handling
Structure
checking and
repair	Optional: re-propose a corrected
region from the error messages	All checks in Table 4; snapping, gap closing,
rejecting invalid output
Responsibility	AI component	Deterministic code
Dimensions and
scale	None in the core workflow	Scale from the user's known dimension;
areas and lengths computed from the wall
graph
3D construction	None	Wall extrusion, opening cut-outs, floors,
ceilings, glTF export
Chat editing	Understands the request and
selects tool and arguments	Executes tools, checks rules, versions, undo
Communication	Drafts short captions for shared
renders	Telegram sending
Geometry model and consistency. Every design, whether it comes from chat or from an image, is stored in one structure, a wall graph , so that the same rules apply to generated plans, imported plans and edits:

Vertices are points on a snapping grid (for example 0.25 ft). Wall ends that should meet have identical coordinates.

Walls are edges between two vertices, with a class (exterior or interior) and a thickness. A wall between two rooms exists once and is referenced by both rooms, which is how shared boundaries are represented.

Rooms are closed loops of wall edges with a type label. Because neighbouring rooms are built from the same shared edges, gaps and overlaps between them cannot arise by construction.

Junctions. Where one wall ends on the middle of another, or two walls cross, code splits the wall at that point and adds a vertex, so every intersection is an explicit shared vertex.

Openings (doors and windows) are stored relative to their wall: wall, offset from the wall start, width, sill height and height. They therefore stay on their wall when other parts of the layout change.

Dimensions (room width, length, area) are computed by code from the wall graph; they are never stored separately and never taken from the model.

The first version supports orthogonal layouts (horizontal and vertical walls), which cover most residential plans in the target market. Diagonal and curved walls are out of scope, and imported plans are simplified to orthogonal geometry.

Table 4. Geometry rules checked after generation, import and every edit

Rule	How it is checked	If it fails
Closed rooms	Every room is a closed loop of wall edges; no
dangling wall ends	Snap within tolerance;
otherwise flag
Shared boundaries	Adjacent rooms use the same wall segment; room
polygons do not overlap or leave gaps above the
tolerance	Merge or snap edges;
otherwise reject
Rule	How it is checked	If it fails
Junctions	Every wall crossing or T-contact is a vertex	Split walls automatically
Valid openings	Each opening lies fully inside one wall and does
not overlap another opening	Clamp or move;
otherwise flag
Minimum sizes	Rooms, doors and windows exceed minimum
dimensions	Warn (room) or reject
(opening)
Access	Every room is reachable from the entrance
through doors	Add a door on a shared
wall (generation) or flag
Boundary	All rooms lie inside the stated plot outline
(generation)	Rescale or reject
Keeping the layout consistent after edits. Each edit tool changes the wall graph through the same functions used for generation, and then the full rule set in Table 4 runs again. If any rule fails, the edit is rolled back and the user is told which rule blocked it. Only operations that cannot disturb a shared wall are supported at first (Table 5). Operations that move shared walls need neighbouring rooms to be recomputed and are supported only after the core operations pass all consistency tests.

Table 5. Chat edit operations

Operation	Rule it must keep	Status
rename_room	None (label only)	Core
add_window, add_door	Opening fits inside the wall, does not
overlap another, and keeps access	Core
move_door, move_window	Stays on the same wall; no overlap	Core
resize_opening	Fits the wall; no overlap	Core
delete_opening	All rooms stay reachable	Core
undo	Restores the previous version	Core
resize_room, move_wall	Shared walls move together; neighbours
stay closed and gap-free; dimensions
propagate	Extended: first for
rooms whose moving
wall is exterior, then
for shared walls,
once the core
operations pass all
tests
5. Generative AI Techniques
Plan2Walk uses five of the technique categories in the assignment, including agentic tool calling, and one real external integration.

Table 6. Techniques, where they are used and candidate models

Technique	Where used and why	Candidate models and tools
Foundation
model (API)
with multimodal
input and
structured JSON
output	Layout generation from chat; plan reading from
images; edit-command understanding with
function calling	Google Gemini API free tier
(Flash and Flash-Lite models
with vision and structured
output); other free options
(Groq, OpenRouter free
models) as fallback
Prompt
engineering	System prompts with the layout schema, few-
shot examples from CubiCasa5K and hand-made
plans, versioned prompt templates	Prompt templates kept in the
repository
Agents and tool
calling	Edit agent calls typed tools (rename_room,
add_window, add_door, move_opening,
resize_opening, delete_opening, undo)	Function calling via the
provider SDK or a small
LangGraph graph
Structured
output and
reliability	Pydantic validation, one retry with error
messages, fallback to a stronger model, human
review of flagged items	Pydantic, JSON schema,
constrained decoding where
available
Multimodal and
documents	OCR hints for room labels and dimensions on
uploaded plans; PDF page rendering	Tesseract or PaddleOCR,
PyMuPDF
Integrations and
automation	Telegram bot sends the render and glTF file;
background job queue	Telegram Bot API, FastAPI
background tasks
Open-source
model and fine-
tuning
(conditional)	A small open VLM is evaluated as a local option;
QLoRA fine-tuning is tried only if the measured
gap and the compute budget justify it (Section
13)	Qwen2.5-VL, Florence-2; PEFT
with QLoRA on Google Colab
Tool calling is controlled. Each tool is a typed function with a schema; arguments are checked before execution (for example the room exists, the opening fits the wall). A change is shown as a preview and applied only after the user approves it, and every change is stored as a version so it can be undone. Specific model versions will be fixed at the start of implementation and logged with every call. Every model and tool used in this project is free: the Gemini API free tier, free open models, Google Colab's free tier and open-source libraries.

6. Technical Alternatives
In the R&D track the comparison of plan-reading approaches is the main research experiment (Section 13). The other tasks are compared as engineering decisions on held-out test sets, and the number of conditions is kept small.

Table 7. Technical alternatives to be compared

Task	Alternatives	Decision criteria
Plan image to	C0 classical pipeline (OpenCV line detection plus	Room IoU, room-type
layout (research
experiment)	Tesseract); C1 prompted API VLM with few-shot
examples; C2 C1 plus deterministic validate-and-
repair; C3 (optional) small open VLM, prompted	accuracy, door and window
F1, geometry-valid rate,
latency, cost
Requirements	G0 single-shot LLM layout with no validation; G1	Requirement satisfaction,
to layout	LLM layout with validate-and-repair; two free-tier
models (for example Gemini Flash and Flash-Lite)
compared for each	geometry-valid rate,
latency, cost
Chat edit
understanding	Rule-based command parser (patterns); API model
with function calling	Tool-call accuracy, edit
success rate, latency, cost
The choice is made on measured accuracy first, then geometry validity, latency, cost and privacy. A cheaper or local model is preferred when it is within about two percentage points of the best option.

7. Data
Plan2Walk needs plans with ground truth for evaluating plan reading, requirement descriptions for evaluating layout generation, and edit commands for evaluating the agent.

Table 8. Data sources

Data	Source and size	Use
CubiCasa5K	Public dataset of about 5,000 annotated floor
plans with vector annotations of rooms, walls,
doors and windows (licence terms to be
confirmed on the dataset page)	Converted to the
layout structure; at
least 50 verified
plans held out as the
test set; a separate
small set of plans for
few-shot examples
Local plans	About 20 to 30 plans from consenting
families, builders and public sample plans,
annotated by the team	Descriptive check of
transfer to local plan
styles; demo
Requirement descriptions	About 60 written descriptions (plot size,
rooms, sizes, adjacencies, preferences), each
with a machine-readable requirement set; 10	Evaluating layout
generation
Data	Source and size	Use
for development, at least 50 for testing	
Edit commands	About 100 commands with the expected
change to the layout (50 for development, 50
for testing)	Evaluating the edit
agent
Converting CubiCasa5K to the layout structure. CubiCasa5K provides each plan as an image with vector annotations in which rooms, walls, doors and windows are polygons or icons with class labels (the team will confirm the exact format against the dataset documentation). The conversion script works in these steps: (1) map the dataset's room classes to a small set (bedroom, bathroom, kitchen, living room, hall, other); (2) take the wall polygons, compute wall centrelines, snap their ends to the grid and split them at junctions to form the wall graph; (3) simplify each room polygon to an orthogonal polygon of at most about eight vertices and express it as a loop of wall edges; (4) attach each door and window to the nearest wall by projecting its centre onto that wall, which gives the offset and width; (5) run the same validator used by the product. Plans are in pixel units, so coordinates are normalised by plan size and the evaluation does not need real-world scale.

Verifying the conversion. Conversion quality is measured in three ways. First, each converted scene is rendered back to room masks and compared with the original room polygons using IoU; plans below a mean IoU of 0.85 are excluded and the share excluded is reported. Second, every converted scene must pass the validator. Third, both members compare 50 randomly selected conversions with the original images and record the errors by type (merged rooms, shifted openings, lost walls). The test set is drawn only from verified conversions, and the paper states which kinds of plans the conversion cannot represent, for example diagonal walls.

Annotation and splits. Local plans and requirement sets are annotated by both members independently on 20 percent of the items, with agreement checked by room matching (IoU above 0.5) and Cohen's kappa for room types (target 0.7 or higher). Development data are used only for prompts and tuning, and test data only for final configurations.

Privacy. Plans from real families can reveal addresses and names. Consent is obtained, text that identifies people or locations is removed or masked, and local plans are not published in the public repository. Uploaded plans in the deployed demo are deleted after a retention period and are never used for training without consent. Because the free tier of the Gemini API may use submitted content to improve Google's products, only synthetic, public or explicitly consented plans are sent to it; private family plans are not.

8. Evaluation Plan
Every AI component is evaluated on held-out data that is not used for prompts. The evaluation measures not only whether the geometry is valid, but also whether the layout is faithful to the original plan (for imports), satisfies the user's requirements (for generation), and changes only what the user asked for (for edits). In Assignment 3 each implemented component is tested on at least 50 examples; in Assignment 4 test sets grow and include harder cases.

Table 9. AI component evaluation and initial targets

AI
component	Metrics	Initial target
Plan import:
fidelity	Room IoU after matching rooms to the ground
truth; room-type accuracy; door and window F1
with a position tolerance; room-count error	Mean room IoU of at least 0.70;
room-type accuracy of at least
80%; door and window F1 of at
least 0.6
Plan import:
validity	Share of imported layouts that pass all rules in
Table 4, before and after repair	At least 90% after repair
Layout
generation:
requirement
satisfaction	Room count and types match; share of requested
rooms with area within 15% of the request; share
of requested adjacencies satisfied; plot boundary
respected	At least 90% counts and types; at
least 80% areas; at least 75%
adjacencies
Layout
generation:
validity	Share of generated layouts that pass all rules in
Table 4, before and after repair	At least 95% after repair
Chat edit
agent	Correct tool and arguments; edit success (the
resulting layout equals the expected layout, and
nothing else changed); invalid edits blocked	At least 90% tool and arguments;
at least 85% edit success; 100%
of invalid edits rolled back
All
components	Latency (median and 95th percentile), cost per
request, failure and fallback rate	Under 60 seconds per generation
or import; free-tier quota
respected, with the equivalent
list-price cost also reported
At system level the team measures the end-to-end success rate (request to valid 3D model without manual repair), tool-call success rate, and tokens and equivalent list-price cost per completed request (the project itself runs on free tiers). At user level, five to ten volunteers (builders, relatives, classmates) answer layout questions (for example how many rooms there are, which room is largest, where the kitchen door is) using the 2D plan only and then using the 3D walkthrough; the team records correctness, time and a short satisfaction rating. Error analysis groups failures by cause (merged rooms, missed doors, wrong labels, invalid JSON, requirement not met, wrong edit target) and guides improvements between Assignments 3 and 4.

9. Deployment Plan
The frontend is hosted on Vercel's free plan, and the backend runs in a Docker container on a free-tier host (for example a Hugging Face Space), so deployment has no cost. Free hosts can sleep when idle and have limited memory, so the backend is kept light: all AI work is done through free API calls and no model is hosted on the server. If a small open VLM is evaluated or fine-tuned (Section 13), the experiments run on Google Colab's free tier (T4 GPU) with checkpoints saved to Google Drive, and the model is added to the deployed product only if it can run within free limits. The whole system also starts from the repository with Docker Compose and a setup guide in the README, so that it can be reproduced locally. GitHub Actions, which is free for public repositories, runs unit tests (geometry

validator, edit tools) and a small evaluation set on each change. All the tools used (Next.js, FastAPI, SQLite, Three.js, Tesseract, the Telegram Bot API) are free or open source.

10. Funding and Business Model
Target customers and market. The customers are small and medium home builders, contractors, realestate agents and developers, and homeowners who pay per design. Pakistan has a large informal construction market where plans are produced by a draftsman on paper or as a simple CAD export. The team will estimate the number of active builders and housing schemes in its home city from public sources before the final pitch (Assignment 4). The first target is one or two local builders for a free pilot.

Operating cost estimate. The prototype built in this course runs entirely on free tiers, so its monthly cost is zero (Table 10). The last column shows indicative costs for a pilot of about 300 designs and 3,000 edit commands per month at one customer, which would start only after funding. Figures are indicative and will be replaced with measured values; token counts are logged for every request.

Table 10. Indicative monthly operating cost (pilot)

Item	Course prototype (free)	Cost
now
(USD
per
month)	Indicative pilot after
funding (USD per
month)
Backend
hosting	Free container host or Hugging Face Space	0	0-20
Model API	Gemini API free tier (Flash and Flash-Lite)
within its request limits	0	15-40
GPU	Google Colab free tier, for experiments only	0	0-60 (only if a fine-
tuned open model is
deployed)
Storage and
domain	Free-tier storage and a free subdomain	0	5-15
Frontend and
monitoring	Vercel free plan and structured logs	0	0-10
Total		0	20-145
Revenue model. A freemium model: a limited number of free designs per month with a watermark on exports, then pay-per-design or a monthly subscription for builders and agents, plus a paid tier for batch processing and white-label embeds on a builder's website.

Seed funding plan. The team will research the current eligibility and application steps for the sources in Table 11 and record the findings before the final pitch. The details below are expected fits and will be verified on each programme's official page.

Table 11. Seed funding and support sources

Source	What it may offer	Fit and requirements to verify
National Incubation Center
(NIC) Karachi or another
national incubation centre	Cohort-based incubation,
mentorship, workspace,
sometimes grants and cloud
credits	Open calls and intake dates; needs a
working MVP and a committed team
Google for Startups Cloud
Program	Cloud credits for early-stage
startups	Requires a working MVP, business
model and company website
Microsoft for Startups	Azure credits and AI tools	Online application; credit levels
(Founders Hub)		depend on milestones
Pakistan Startup Fund or
similar government funds	Equity-free grants alongside
private investment	Needs a private investor first; check
current rounds
Minimum viable product. The user describes a single-storey home in chat (or uploads a plan), receives a validated 2D layout, walks through the 3D model, makes a few reliable chat edits, and shares a render.

Table 12. Lean Canvas for Plan2Walk

Block	Content
Problem	Clients cannot visualise 2D plans or describe a design to a
draftsman; 3D renders are costly and slow; changes cause
rework and mistakes found late
Customer segments	Homeowners; small builders and contractors; property agents;
early adopters are builders who already show plans to clients
Unique value proposition	Describe your home or upload your plan and get an editable 3D
walkthrough in about a minute, with geometry checked by
code, not guessed by AI
Solution	Chat-first layout generator with plan import, geometry
validator, automatic 3D builder, chat editing with typed tools,
sharing
Channels	Direct pilots with builders, real-estate groups and social media,
builder associations, embeddable viewer on builders' websites
Revenue streams	Pay-per-design, monthly subscription, white-label embed, batch
processing
Cost structure	Hosting, model API, optional GPU, support, data labelling
Key metrics	Designs created per month, share needing no manual
correction, time to first 3D view, repeat usage, paid conversion
Block	Content
Unfair advantage	A verified layout schema and conversion pipeline, a tested edit-
tool set, and a growing set of local plan styles and requirement
descriptions
11. Risks and Responsible AI
Plan2Walk must never silently present an invented layout as fact. The interpreted requirements are shown to the user before a layout is generated, uncertain items are marked in the layout view for confirmation, and the output is described as a visualisation, not a construction drawing.

Table 13. Main risks and safeguards

Risk	Effect	Safeguard
Layout ignores or
misreads the
requirements	Design does not
match what the
user asked for	Interpreted requirement set shown to the user;
code checks room counts, sizes and adjacencies
against it and reports mismatches
Wrong room or wall
extraction from an
uploaded plan	Wrong 3D model	Overlay shown on the original; user confirmation;
manual correction
Invalid JSON or
geometry	Crash or distorted
model	Pydantic schema, validator, one retry with errors,
fallback model, flagged items
Wrong scale or
dimension	Misleading room
sizes	User must confirm one known dimension;
dimensions computed by code
Domain shift (Finnish
training and few-shot
plans, local test plans)	Lower accuracy on
local plans	Local plans measured separately; local few-shot
examples; the gap is reported openly
Unsafe or inconsistent
edit	Impossible design,
broken shared walls	Typed tools, full rule check after every edit, rollback,
preview before commit, undo; only wall-safe
operations at first
Ambiguous chat
command	Wrong room or
opening changed	The agent asks which element is meant when more
than one matches
Prompt injection
through text on a plan
or in a chat message	Model follows
hidden instructions	Plan text treated as data; tool calls limited to the
layout; no code or file-system access
Over-reliance as a
construction drawing	Real-world errors	Clear notice that output is for visualisation only, not
structural or approved design
Privacyof uploaded	Exposure of home	Access control,retention limit,no traininguse
Risk	Effect	Safeguard
plans	layouts	without consent
API quota or outage	Service pauses	Caching, per-user limits, evaluation runs spread over
when the free	several days, fallback to another free provider or a
quota is used up	local open model, usage logged per request
The user always has the final say over the layout and every edit. Every edit is versioned and logged.

12. Work Plan and Team Roles
The project is delivered in two parts. Assignment 3 implements about 40 to 45 percent of the complete product (a working end-to-end slice of the core workflow) and the first evaluation. Assignment 4 completes the remaining core functionality, the full evaluation and the research paper. Extended features are planned for after the core workflow is complete and are not part of the committed scope.

Table 14. Scope of each project part

Part	Product work	Research and evaluation work
Assignment 3
(about 40-
45%)	F1 for single-storey rectangular layouts; F2 with
a user-supplied scale and a prompted API VLM;
F3 with the core rules (closed rooms, shared
boundaries, junctions, valid openings); F4 read-
only 2D view with rename; F5 3D walkthrough;
F6 with three operations (rename_room,
add_window, move_door and move_window);
F7 versions and undo; Telegram render sharing;
Docker setup; first deployment	CubiCasa5K conversion and its
verification; test sets (at least 50
verified plans, 50 requirement
descriptions, 50 edit commands);
conditions C0, C1, C2 for plan
import and G0, G1 for generation;
edit-agent tests; error analysis
with at least ten failures; latency
and cost
Assignment 4
(final)	Remaining edit operations (add_door,
resize_opening, delete_opening); remaining
rules (access, minimum sizes, boundary); F4
manual correction; F8 glTF export; robustness
and deployment hardening; extended features
only if the core is complete	Full test sets and local plans;
ablations; repeated runs and
significance tests; user study; the
fine-tuning decision (Section 13);
research paper, documentation
and reproducibility package
Table 15. Team roles
Member	Primary responsibilities	Also contributes
Hamna Asif (AI	Layout specification and prompts, plan-reading	Chat panel and upload in the
and research	VLM, edit agent and tool schemas, CubiCasa5K	frontend; geometry validator
lead)	conversion and verification, evaluation code and
metrics	tests
Ayesha Noor	Wall-graph builder and geometry validator, edit tool	Classical CV baseline (C0);
(backend and	engine,FastAPI and database,Three.js viewer and	localplan collection and
Member	Primary responsibilities	Also contributes
3D lead)	3D scene builder, Docker and deployment, Telegram
bot	annotation; user study
Table 16. Milestones

Week	Milestone	Main outputs
1	Design and data	Layout specification and wall-graph schema, tool
schemas, repository, first version of the CubiCasa5K
conversion script
2	Generation and validation	Layout generator from chat, wall-graph builder,
validator with the core rules, first 2D view
3	Import, 3D and editing	Prompted VLM import, 3D viewer, three edit
operations with rollback, conversion verification, C0
baseline
4	Assignment 3 demonstration	Deployed slice, test sets, comparison of C0, C1, C2 and
G0, G1, edit tests, error analysis, latency and cost
5	Remaining core features	Remaining edit operations and rules, manual
correction, glTF export
6	Full evaluation	Larger test sets, local plans, ablations, repeated runs
7	Analysis and hardening	Statistics, user study, fine-tuning decision, robustness
tests, CI
8	Assignment 4 submission	Paper, reproducibility package, documentation,
investor pitch
Both members review each other's pull requests, and each must be able to explain the whole system and the experiments in the viva.

13. Track-Specific Plan (R&D Product)
Related work. Early deep-learning work showed that wall, room and icon structure can be recovered from raster floor plans [1], and the CubiCasa5K dataset gave a larger annotated benchmark with room, wall, door and window labels [2]. These methods output segmentation or vector primitives for a fixed set of classes, tuned to the style of their training data. Generative layout models such as House-GAN and HouseDiffusion generate plans from constraints rather than read existing ones [3][4]. Vision-language models now read documents and screenshots without hand-built pipelines: Pix2Struct and Donut learn to parse documents into structured text [5][6], Florence-2 provides a compact multi-task vision model [7], and the Qwen2-VL and Qwen2.5-VL series offer open VLMs with strong document and image understanding at small sizes [8][9]. Parameter-efficient adaptation with LoRA and QLoRA makes adapting such models possible on a single modest GPU [10][11]. For editing, models that reason and act

with tools provide the basis for agents [12], and tool-use training shows models can learn when to call functions [13]. Constrained decoding can force outputs to follow a schema [14].

Research gap. We found no study that compares a prompted VLM and a classical CV and OCR pipeline for producing editable, geometry-valid floor-plan layouts, measures how much a deterministic validateand-repair loop improves validity without lowering fidelity to the original plan, and reports how the results transfer to local South Asian plan styles. The team will confirm this gap with a literature search before submission and revise it if related work is found.

Primary research question and hypotheses. The research is limited to one primary question, which directly concerns the product's plan-import path.

Table 17. Research question and hypotheses

ID	Research question	Hypothesis
RQ1 (primary)	How do a classical CV and OCR pipeline (C0),
a prompted API VLM (C1) and a prompted
API VLM with deterministic validate-and-
repair (C2) compare in converting floor-plan
images into layouts that are both
geometrically valid and faithful to the
original plan?	H1: C2 raises the geometry-
valid rate by at least 20
points over C1, and C1 and
C2 reach a room IoU at
least 0.10 above C0. H2:
repair does not lower
fidelity: mean room IoU of
C2 stays within 0.02 of C1.
Engineering question	Does validate-and-repair also improve
generated layouts, measured by validity and
by how well they satisfy the user's written
requirements (G0 against G1)?	No formal hypothesis;
reported with the targets in
Table 9
Experimental design. The experiment compares C0, C1 and C2 on the verified CubiCasa5K test plans (at least 50 in Assignment 3, about 100 in Assignment 4) using the metrics in Table 9, and reports the same measures descriptively on the 20 to 30 local plans. An optional condition C3 runs a small open VLM with the same prompt. All conditions use the same prompts, test plans and recorded model versions. Requirement-to-layout generation (G0, G1) and edit understanding are evaluated as engineering comparisons on their own test sets.

Fine-tuning decision. QLoRA fine-tuning is not part of the initial product. The performance of existing VLMs is established first. A QLoRA run (condition C4) is added in Assignment 4 only if two conditions hold: a small open VLM (C3) is clearly behind the API VLM in a way that matters for the product, for example by more than 10 points in room-type accuracy, and a run is feasible on free Colab (a T4 GPU, short outputs from the compact layout specification, images at reduced resolution, about 1,000 training plans for one to two epochs with checkpoints saved to Drive). If either condition fails, fine-tuning is reported as future work.

Table 18. Ablation studies (kept to two)

Factor	Settings compared	Purpose
Factor	Settings compared	Purpose
Repair loop	None vs rule-based repair vs rule-based repair plus	Contribution of validation to
one model retry	validity and fidelity
OCR hints	With vs without Tesseract text given to the VLM	Effect on room labels
Metrics and statistical analysis. Plan import is measured with room IoU after matching, room-type accuracy, door and window F1 and geometry-valid rate. Each condition is run three times with different sampling seeds and reported as mean and standard deviation, and test-set uncertainty is reported with bootstrap confidence intervals. Conditions are compared with paired bootstrap tests for continuous metrics and McNemar tests for per-plan outcomes, with Holm correction for multiple comparisons.

Threats to validity. CubiCasa5K contains mostly Finnish apartment plans, so results may not generalise; the local plans are few and are used descriptively. The converted ground truth simplifies the original annotations, which is why conversion quality is measured and reported (Section 7). The team annotates the local plans itself, which is addressed by written guidelines and agreement checks. Commercial models change over time, which is addressed by logging versions and repeating key runs near submission.

Expected contributions. A deployed chat-first plan-to-3D product; a layout schema with a verified CubiCasa5K conversion pipeline and a small set of requirement descriptions and edit commands; and a controlled comparison of classical and prompted approaches with a validate-and-repair loop, including its effect on fidelity.

Target venue and reproducibility. The target is a short paper at an applied vision, documentunderstanding or AI-in-construction workshop, or a relevant student or demonstration track. The reproducibility package will contain code, configuration, conversion scripts, experiment logs and a script that regenerates the main results tables.

References
[1] C. Liu, J. Wu, P. Kohli, Y. Furukawa, Raster-to-Vector: Revisiting floorplan transformation, in: ICCV, 2017. arXiv:1708.01871.

[2] A. Kalervo, J. Ylioinas, M. Häikiö, A. Karhu, J. Kannala, CubiCasa5K: A dataset and an improved multitask model for floorplan image analysis, in: SCIA, 2019. arXiv:1904.01920.

[3] N. Nauata, K.-H. Chang, C.-Y. Cheng, G. Mori, Y. Furukawa, House-GAN: Relational generative adversarial networks for graph-constrained house layout generation, in: ECCV, 2020. arXiv:2003.06988.

[4] M. A. Shabani, S. Hosseini, Y. Furukawa, HouseDiffusion: Vector floorplan generation via a diffusion model with discrete and continuous denoising, in: CVPR, 2023. arXiv:2211.13287.

[5] K. Lee et al., Pix2Struct: Screenshot parsing as pretraining for visual language understanding, in: ICML, 2023. arXiv:2210.03347.

[6] G. Kim et al., OCR-free document understanding transformer (Donut), in: ECCV, 2022. arXiv:2111.15664.

[7] B. Xiao et al., Florence-2: Advancing a unified representation for a variety of vision tasks, in: CVPR, 2024. arXiv:2311.06242.

[8] P. Wang et al., Qwen2-VL: Enhancing vision-language model's perception of the world at any resolution, 2024. arXiv:2409.12191.

[9] S. Bai et al., Qwen2.5-VL technical report, 2025. arXiv:2502.13923.

[10] E. J. Hu et al., LoRA: Low-rank adaptation of large language models, in: ICLR, 2022. arXiv:2106.09685.

[11] T. Dettmers, A. Pagnoni, A. Holtzman, L. Zettlemoyer, QLoRA: Efficient finetuning of quantized LLMs, in: NeurIPS, 2023. arXiv:2305.14314.

[12] S. Yao et al., ReAct: Synergizing reasoning and acting in language models, in: ICLR, 2023. arXiv:2210.03629.

[13] T. Schick et al., Toolformer: Language models can teach themselves to use tools, in: NeurIPS, 2023. arXiv:2302.04761.

[14] B. T. Willard, R. Louf, Efficient guided generation for large language models, 2023. arXiv:2307.09702.

Online Resources and AI Tool Declaration
CubiCasa5K dataset page; Hugging Face model pages for Qwen2-VL, Qwen2.5-VL and Florence-2; Three.js documentation. NIC Karachi: https://nickarachi.com; Google for Startups Cloud Program: https://cloud.google.com/startup/faq; Microsoft for Startups Founders Hub: https://foundershub.startups.microsoft.com.

AI tool declaration. An AI assistant (Claude) was used to brainstorm project ideas, draft this proposal and review its structure against the assignment rubric. The team reviewed, edited and verified the content. AI tools used while writing code will be declared with the repository.