# Lia - Local Intelligence Assistant

A CLI tool for interacting Lia in various forms.

## Installation

- Create a python environment:
```
conda create -n lia python=3.12
conda activate lia
```
- Clone the repository
```
git clone git@github.com:nssac/lia.git
```
- Do a local dev install of lia
```
    cd lia
    pip install -e .
```
*Note, I have not fully tested that I have everything currently needed defined in the pyproject.toml.  If you find you need to pip install something. Please add it to the pyproject.toml or let me know (dm8qs@virginia.edu)*

- Install ollama (https://ollama.com/download)
- Install Apptainer (note this generally means running this on Rivanna with module load apptainer or running on a local linux machine with apptainer installed)

## Usage
```
$ lia --help
Usage: lia [OPTIONS] COMMAND [ARGS]...

Options:
  --install-completion [bash|zsh|fish|powershell|pwsh]
                                  Install completion for the specified shell.
  --show-completion [bash|zsh|fish|powershell|pwsh]
                                  Show completion for the specified shell, to
                                  copy it or customize the installation.
  --help                          Show this message and exit.

Commands:
  ateam     Start the interactive chat with ATeam.
  lia       Start the interactive chat with Lia.
  reasoner  Start the interactive chat with reasoner.
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


### Automoteam
Automoteam is an swarming reasoner.  Given an objective it assembles a team of agents to consider and execute the objective. 
When the objective is provide, it first determines (generates) which kinds of real world 'experts' would be good for addressing the object (2-5 in total). For each of these experts, it generates a name and an LLM sytem prompt declaring them as the experts they are.
Then, using a 'create_team' tool, the system then instantiates each of these agents.
The objective is provided to them by the leader and then they engage in discussion between themselves and leader.  The leader may also ask the user follow questions.

### Reasoner
The Reaoner is similar to the Automoteam, except that it has a fixed size team with a different set of prompts.  In this case it is setup as a left brain/right brain agents interacting with the leader.  
The left brain/right brain are told they are representing the left or right hemisphere, but mainly their difference is that the left brain is given a low temperature when when submitting to the model and the right brain is given a high temperature when submitting.

### Tools
There are a few tools in here, most have only recently been developed and are not fully deployed throughout all of the subsystems of lia.
- Python execution tool
    Given a python script as a string, this tool will execute the python code in a sandboxed environment. 


