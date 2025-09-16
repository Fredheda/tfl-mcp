# TFL Line Status API (with MCP)

Welcome to the TFL Line Status API project! 🚇

This project implements a simple MCP server. Its purpose is to fetch and processes real-time status information for London Underground lines using the official TFL API.

## Features
- Fetches live status for all major London Underground lines
- Processes and formats the data as JSON
- Example code for both script and notebook usage
- Creates for integration with MCP (Model Context Protocol)

## Quickstart

### 1. Clone the repo
```sh
git clone https://github.com/Fredheda/tfl-mcp.git
cd tfl
```

## MCP Server Usage

This project is a ready-to-run MCP (Model Context Protocol) server. When you run `python tfl.py`, it starts an MCP server that you can connect to with:

- **Claude Desktop**: Add a new MCP server and point it to your running instance.
- **Your own MCP client**: See the [Model Context Protocol documentation](https://modelcontextprotocol.io/docs/develop/build-server) for details.



### 2. Set up your environment (Recommended: [uv](https://docs.astral.sh/uv/))
```sh
python3 -m venv .venv
source .venv/bin/activate
uv pip install -e .
```

This project uses a `pyproject.toml` for dependencies. If you don't have `uv`, you can use:
```sh
pip install -e .
```

### 3. Run the script
```sh
uv run tfl.py
```