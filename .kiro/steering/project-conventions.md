---
inclusion: always
---

# Project Conventions

## AWS CLI

- Always use `--profile=mondayskills.development` for all AWS CLI commands.

## Docker

- Always use `--platform=linux/amd64` as the build target for Docker builds.

## VPC

- Always use existing VPC `vpc-0a2290ed34b346805`. Never create a new VPC.

## CloudWatch Logs

- When viewing ECS/dbt task logs in this environment, use log group: `EtlComputeStack-DbtTaskDefinitionDbtContainerLogGroupE420E81B-W7fZGqD3w8jD`.

## Project Structure

- `/iac` — AWS infrastructure code (IaC).
- `/etl` — dbt code (data transformation).
- `/viz` — Streamlit visualization code.

## Changelog

- Always update `CHANGES.md` at the project root when making code changes. Add a new entry at the top (below the heading) with a summary and list of files changed. Follow the existing format in the file.
