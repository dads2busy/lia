# Lia - Local Intelligence Assistant

A CLI tool for interacting Lia in various forms.

## Installation
- Clone the repository
```
git clone git@github.com:nssac/lia.git
cd lia
```
- Create a python environment:
```
conda create -n lia python=3.12
# or `conda env create -f conda_env.yml` # provisioned sandbox; but might mask deficient Python package deps
conda activate lia
```

- Do a local dev install of lia
```
    pip install -e .
```
*Note, I have not fully tested that I have everything currently needed defined in the pyproject.toml.  If you find you need to pip install something. Please add it to the pyproject.toml or file an issue with the project*
Some/much of the folowing may not be necessary if you start with the conda_env.yml file.
- Install [ollama](https://ollama.com/download).
- Install Apptainer 
## Usage
```
$lia --help
                                                                                                                                                      
 Usage: lia [OPTIONS] COMMAND [ARGS]...                                                                                                               
                                                                                                                                                      
╭─ Options ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --install-completion          Install completion for the current shell.                                                                            │
│ --show-completion             Show completion for the current shell, to copy it or customize the installation.                                     │
│ --help                        Show this message and exit.                                                                                          │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ generate-material-network       Start the Material Network Generator                                                                               │
│ generate-supply-chain-network   Start the Supply Chain Network Generator                                                                           │
│ reasoner                        Start the interactive chat with reasoner.                                                                          │
│ ateam                           Start the interactive chat with ATeam.                                                                             │
│ lia                             Start the interactive chat with Lia.                                                                               │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯$
```

The base ```lia lia``` command will have you interacting with the "context_manager_agent".  You can establish a differnet default agent, with ```-a <agent>```, for example ```lia lia -a supply_chain_agent```.

Two other setups for lia are the Automoteam (ateam) and the Reasoner.

To launch Automoteam:
```lia ateam``` or ```lia ateam -r``` if you want to see the inter agent communcations.

To launch Reasoner:
```lia reasoner``` or ```lia reasoner -r``` if you want to see the inter agent communcations.

The LLM api url defaults to localhost, but if you are using Rivanna or some other location for your
LLM Inference engine, use --llm-api-url.
```lia reasoner --llm-api-url=http://udc-an36-25:11434/v1```

There is also a non-interactive script to generate a supply chain network:
```lia generate-supply-chain-network -o atmega32p.json "ATmega328P"```
This script takes the first argument, generate the network, and writes the output to --output/-o

### Automoteam
Automoteam is an swarming reasoner.  Given an objective it assembles a team of agents to consider and execute the objective.
When the objective is provide, it first determines (generates) which kinds of real world 'experts' would be good for addressing the object (2-5 in total). For each of these experts, it generates a name and an LLM sytem prompt declaring them as the experts they are.
Then, using a 'create_team' tool, the system then instantiates each of these agents.
The objective is provided to them by the leader and then they engage in discussion between themselves and leader.  The leader may also ask the user follow questions.

### Reasoner
The Reaoner is similar to the Automoteam, except that it has a fixed size team with a different set of prompts.  In this case it is setup as a left brain/right brain agents interacting with the leader.
The left brain/right brain are told they are representing the left or right hemisphere, but mainly their difference is that the left brain is given a low temperature when when submitting to the model and the right brain is given a high temperature when submitting.

### Generate Material Network
This is the bottom-up network generator.  

It depends on an externally run mcp server (locally running) for the HS Code resolution.  You can launch that tool like this:
```cd src/lia; python tools/mcp-server-hscode-vector-rollupmd.py```

Note: This mcp server is currently expecting to run on Rivanna to have access to /sfs/gpfs/tardis/project/bi_dpi/data/UN_Comtrade/H6_rollup.md.  To run locally, make sure the file is available locally and then run it the mcp server with ```--file /path/to/H6_rollup.md```.

Once the mcp server is running (and says that it is listening, it will take a couple mins), you can launch the generator:

```lia generate-material-network -o output.json -m gpt-4.1-mini --llm-api-key $OAIKEY "boron"```

Options:
```
$ lia generate-material-network --help
                                                                                                
 Usage: lia generate-material-network [OPTIONS] MATERIAL...                                     
                                                                                                
 Start the Material Network Generator                                                           
                                                                                                
                                                                                                
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────╮
│ *    material      MATERIAL...  [default: None] [required]                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────╮
│ --output         -o      TEXT     Output file.  If not provided, output stdout               │
│                                   [default: None]                                            │
│ --prelim-only    -P               Only perform the preliminary analysis, no network          │
│                                   generation                                                 │
│ --prelim-out     -p      TEXT     Output for Preliminary Research. Do not save if not        │
│                                   provided.                                                  │
│                                   [default: None]                                            │
│ --prelim-in      -i      TEXT     Input for Preliminary Research. Uses this data as the      │
│                                   starting point.                                            │
│                                   [default: None]                                            │
│ --prelim-rounds          INTEGER  Number of preliminary research rounds [default: 3]         │
│ --model          -m      TEXT     Default Base Model Name [default: llama3.3]                │
│ --llm-api-url    -u      TEXT     URL to LLM API [default: None]                             │
│ --llm-api-key    -k      TEXT     API Key if needed for LLM [default: None]                  │
│ --help                            Show this message and exit.                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────╯
```

### identify-raw-materials
Attempts to find the raw materials need to produce a product or component along with its HS Code and whether the 
material relationship is direct (ends up in the final product) or indirect (only used in the manufacturing process)

It depends on an externally run mcp server (locally running) for the HS Code resolution.  You can launch that tool like this:
```cd src/lia; python tools/mcp-server-hscode-vector-rollupmd.py```

Note: This mcp server is currently expecting to run on Rivanna to have access to /sfs/gpfs/tardis/project/bi_dpi/data/UN_Comtrade/H6_rollup.md.  To run locally, make sure the file is available locally and then run it the mcp server with ```--file /path/to/H6_rollup.md```.

```
lia identify-raw-materials -o /tmp/raw_material_list.json -m "gpt-4.1-mini" -r 1 -R 2  --llm-api-key $OAIKEY arduino microprocessor
```

Options:
```
$ lia identify-raw-materials --help
                                                                                                                           
 Usage: lia identify-raw-materials [OPTIONS] MATERIAL...                                                                   
                                                                                                                           
 Identify raw materials for a specific technology/product                                                                  
                                                                                                                           
                                                                                                                           
╭─ Arguments ─────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *    material      MATERIAL...  [default: None] [required]                                                              │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ───────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --debug        -d               Enable debugging output.                                                                │
│ --model        -m      TEXT     Default Base Model Name [default: llama3.3]                                             │
│ --llm-api-url  -u      TEXT     URL to LLM API [default: None]                                                          │
│ --llm-api-key  -k      TEXT     API Key if needed for LLM [default: None]                                               │
│ --max-reviews  -R      INTEGER  Maximum number of reviews [default: 3]                                                  │
│ --min-reviews  -r      INTEGER  Minimum number of reviews [default: 1]                                                  │
│ --output       -o      TEXT     Output file.  If not provided, output stdout [default: None]                            │
│ --help                          Show this message and exit.                                                             │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### Tools
There are a few tools in here, most have only recently been developed and are not fully deployed throughout all of the subsystems of lia.
- Python execution tool
    Given a python script as a string, this tool will execute the python code in a sandboxed environment.
