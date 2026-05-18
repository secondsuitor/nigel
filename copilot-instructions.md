# Copilot Instructions for website

## Project Overview
Taking from my previous work: https://github.com/secondsuitor/nigel

This will be a single-user blog, focusing on personal essays, personal data analysis, and effectively a living resume. The design will be minimalist, prioritizing readability and security. Comments may be added later, but that isn't a current requirement. Spinning up new data tables for new features with minimal work is needed. All code must be traceable, readable and documented.
The project will be built in phases, with the first phase focused on getting a working version up quickly, and future phases adding more advanced features and data analysis.
The tech stack will be Python Flask for the backend, PostgreSQL for the database, and minimal JavaScript for any necessary client-side interactions. Hosting will be on Gandi.net's Simple+ hosting plan, which supports Python 3.9 and PostgreSQL 11.
The project will be developed with a focus on privacy, auditability, and minimal dependencies. All user interaction data will be processed locally, and no external libraries will be used without careful vetting for security and necessity. No viewer data will be collected or processed outside of the local environment.
The system will be designed to interfere with scraping.


**Current Phase**: Revuild from repository, getting something up fast. Backups from the Wordpress SIte http://secondsuitor.com need to be imported with correct dates. All authors are me.

**Future Phases**: 
-  Add non-obvious data anlysis (data logging of temperature and then cross correlate with writing frequency, etc). 
-  Add footnote and citation system (everything should be cross-refernced)
-  Auto-post via AT protocol to Bluesky
-  Add static site generation for speed and security
-  Add more advanced data visualizations
-  Auto writing in other voices (think Ender's siblings), based on my prompts, but countered. I write a review indicating how I liked a book, that's fed through a model to write the same review but the opposite side of the coin.

## Architecture & Key Principles

-  Python backend using Flask. 
-  PostrgeSQL for Database. 
-  Minimal to no JS or other workarounds.
-  Hosting is S+ from Gandi.net (Python 3.9, PostgreSQL 11)
-  Minimal external libraries, vetting each one for security and necessity.


### Software Design Principles
- **Privacy First**: No external processing of user interaction data
- **Auditability**: All code must be legible and well-documented
- **Minimal Dependencies**: Vet all external libraries carefully
- **State-Driven**: Non-linear mood responses based on user interaction patterns

## Development Structure

### Directory Layout

## CircuitPython Patterns

## Development Workflow
- Use Git for version control
- Use Git for deployment (see https://docs.gandi.net/en/web_hosting/connection/git.html)
- Write unit tests for all new features

## Style Rules
- No emojis in code or comments
- No non utf-8 characters used in comments, print statements, logs, etc.
- Use 2 spaces for indentation
- Descriptive variable names

---
