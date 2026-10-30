# AI Prompt History

This document records the prompts used while planning, developing, testing, and reviewing the YottaFlex AI candidate project. The prompts are organised by AI tool and project stage to make the development process easier to follow.

Some prompts have been edited for clarity and elaborated to explain the original intention more clearly. They are not necessarily verbatim copies of the original messages. Long documents supplied during the conversations are described in brackets rather than reproduced in full. AI-generated responses are not included.

---

# 1. Claude (Anthropic) – claude.ai

**Project stages:** Planning, understanding, and initial development  
**Date:** October 28–29, 2026  
**Conversation:** One continuous chat

*Note: The following prompts are based on the available Claude chat history. Their wording has been clarified and expanded while preserving the intent of the original messages.*

## Planning and understanding

### 1. Understanding the recruitment challenge

I have received an invitation to participate in a 72-hour recruitment challenge. I will share the invitation details first. Please go through the requirements carefully, especially the deadline, GitHub repository requirements, rules regarding AI tools, and final submission expectations. Help me understand what is expected before we begin implementation.

### 2. Understanding the submission guidelines

I am sharing the company's submission guidelines and candidate FAQ. Please study both documents carefully and explain the important requirements in simple terms. Pay particular attention to executable code, public GitHub repository requirements, AI usage disclosure, prompt history, project documentation, and what the evaluators expect to see.

### 3. Introducing the problem statement

I will now share the actual project problem statement. Please wait until I provide it, then help me understand the problem before suggesting an implementation.

### 4. Analysing the complete problem statement

Please analyse the complete problem statement in detail. The main requirement is to transform clickstream or application events into user sessions using event-time gaps, while handling out-of-order events, duplicate events, missing timestamps, and boundary conditions.

Go through the implementation steps, expected deliverables, edge cases, acceptance criteria, and evaluation weights. Explain what needs to be built and how the different parts of the pipeline should work together.

### 5. Starting from the basics

I am completely new to building this type of data engineering project. Please explain the project from the beginning, including what the problem means, why sessionisation is needed, what the pipeline should accomplish, and which technologies we can use. Avoid assuming that I already understand the tools or concepts.

### 6. Estimating the development time

Based on the problem statement and its requirements, how much actual time would it take to complete this project? Give me a realistic estimate covering environment setup, implementation, testing, debugging, documentation, and final submission preparation.

### 7. Exploring additional features

Would it be useful to include additional technologies or features such as AI, LLMs, workflow orchestration, or monitoring? Please distinguish between features that genuinely improve the project and features that would only add unnecessary complexity. I want the project to remain focused on the original requirements.

### 8. Planning the development schedule

I want to begin setting up the project tonight and complete the main implementation tomorrow. I would prefer to reserve Friday for reviewing, testing, and preparing the submission. Help me organise the work around this schedule and identify what must be completed first.

### 9. Confirming the review schedule

I want to keep Friday specifically for review and final preparation. Please structure the implementation plan so that the core project is completed by Thursday, leaving Friday for verification, corrections, documentation, and submission checks.

### 10. Creating a detailed roadmap

Go through the problem statement again and create a detailed development roadmap. Divide the work into clear sections, explain the objective of each section, list the files or components required, and identify the expected output before moving to the next stage.

### 11. Evaluating the project's practical impact

I want this project to be meaningful beyond simply satisfying a recruitment assignment. Would this solution have practical value in a real-world environment? What would make it useful to a company or client, and what aspects would recruiters appreciate? Please give an honest assessment rather than recommending features just to make the project look bigger.

### 12. Explaining the project as a beginner

I am new to these tools and workflows, although I can complete tasks when guided properly. Please treat me as a beginner and explain each stage in simple language. Before starting implementation, give me a detailed roadmap divided into sections. I will ask you to guide me through each section when I am ready.

### 13. Setting quality expectations

I want the Python scripts, SQL components, and test cases to be written carefully, with proper structure and relevant edge cases. Please pay attention to correctness, maintainability, error handling, and the quality expected in a professional project.

Do not rush through the implementation or assume that a basic working solution is sufficient. When I ask you to start, guide me through the setup and development process step by step, including where to go, which commands to run, which files to create, and how to verify the results.

### 14. Development environment and project ownership

I am using Windows, and the necessary tools are already installed. Please explain how to use the environment and development tools properly rather than assuming I know the workflow.

Other candidates have received the same problem statement, so I want my implementation to demonstrate good engineering practices. Keep track of what we complete and what remains pending. I also want to prepare for an interview-style question-and-answer session on Saturday so I can understand and explain the project independently.

### 15. Beginning implementation and environment setup

Let's start building the project. First, guide me through setting up the development environment, creating the project directory structure, preparing the required files, and installing dependencies. Explain each step and wait for confirmation where necessary so that I do not miss anything.

## Build and prompt-history requests

### 16. Finding the existing project plan

Please locate the Markdown file created by Claude earlier in the project. I want to continue working from the existing planning document rather than creating a separate plan without checking what is already available.

### 17. Completing the project plan

Please complete the existing `PLAN.md` based on the project requirements and the roadmap we discussed. Make sure the plan is structured, covers the necessary implementation stages, and reflects the actual project scope.

### 18. Checking project completion

You previously indicated that the full project had been completed. Please clarify exactly what has been implemented, what has been tested, and what remains unfinished. Distinguish between actual completed work and tasks that still require verification.

### 19. Preparing the prompt history

Please prepare a prompt history documenting the prompts I used while building the project. Keep the prompts organised, preserve their original intent, and make the document suitable for inclusion in the final project repository.

---

# 2. OpenAI Codex – IDE

**Project stage:** Submission review, running the project, and final checks  
**Date:** October 30, 2026

*Note: These prompts are based on the four Codex prompts shared in the project conversation. Wording has been clarified and elaborated.*

### 1. Reviewing the recruitment documents and GitHub requirements

I am providing the recruitment submission guidelines and candidate FAQ. Please read both documents carefully and compare their requirements against the current project.

I particularly want a detailed review of the GitHub-related requirements. Identify what has already been completed, what is missing, and whether anything has been done incorrectly. For every issue, explain which file, setting, or project area needs attention and what should be changed. Do not assume that a requirement has been completed unless there is evidence.

### 2. Evaluating the implementation against the problem statement

I have already shared the original problem statement. Use it as the primary reference while reviewing the current implementation.

Evaluate whether the project solves the actual problem, whether the design is appropriate, and whether the implementation is reliable enough for evaluation. Identify weaknesses, missing edge cases, possible improvements, and areas where the project could be made more practical without introducing unnecessary complexity.

### 3. Beginning the final submission checks

Let's begin the final verification process. You already have context about the project and the work that remains unfinished.

First, help me run the project and verify that it works in the current environment. After that, we will complete the remaining checks one at a time.

Do not commit or push anything to GitHub unless I explicitly instruct you to do so. Keep the current changes available locally until we have reviewed everything and I approve the final Git operations.

### 4. Improving project structure and documenting personal contribution

Although AI tools were used during development, this is my individual recruitment submission, and I am responsible for understanding and presenting the work.

Please help me make the project organised, clear, and professionally structured while strictly following the two recruitment documents I supplied.

Pay particular attention to the following:

- Review `AI_USAGE.md` so that it transparently explains the role of AI tools and accurately reflects my own involvement.
- Review the data dictionary for correctness, completeness, and consistency with the actual implementation.
- Prepare a clear and natural prompt-history document that records the prompts used with the AI tools.
- Improve the organisation and readability of the repository.
- Ensure that the documentation describes the actual implementation rather than making unsupported claims.

Do not make changes that misrepresent my contribution or claim that I personally implemented work that was generated by an AI tool. I want to be able to understand and explain every important part of the project during evaluation.

---

# 3. OpenAI ChatGPT

**Project stage:** Planning, guided implementation, debugging, testing, and review

*Note: This section should contain the actual ChatGPT prompts used during the project. The available conversation context supports the following broad areas of interaction, but it is not a complete verbatim export of every prompt. Entries below are therefore summaries of the interactions, not reconstructed quotations.*

1. **Project understanding and planning:** Discussed the YottaFlex challenge, its requirements, expected deliverables, and a step-by-step implementation roadmap.

2. **Beginner-friendly development guidance:** Requested guidance through the Windows development environment, project setup, folders, files, Python environment, and commands.

3. **Pipeline implementation:** Worked through the modular Python pipeline, including ingestion, validation, deduplication, sessionisation, storage, and reporting.

4. **Testing and debugging:** Reviewed test coverage, investigated implementation issues, and addressed reference validation for an explicitly supplied empty users file.

5. **Benchmark safety:** Reviewed the benchmark's working-directory handling and corrected it so that unrelated files are not deleted.

6. **Performance verification:** Ran a 100,000-row benchmark, reviewed the generated performance report, and examined the incremental session rebuild optimisation.

7. **Submission readiness:** Compared the project against the recruitment requirements and identified remaining work involving reconciliation, edge cases, documentation, GitHub publication, and final verification.

*Transparency note: This section is a summary of available project interactions. It should not be presented as a complete or verbatim ChatGPT prompt export.*

---

# Final note

The purpose of this prompt history is to provide a transparent record of how AI tools supported the project. The prompts show the progression from understanding the challenge and planning the solution to implementation, testing, debugging, and submission preparation.

The candidate remains responsible for reviewing the generated implementation, verifying its behaviour, understanding its design decisions, and being able to explain the submitted work independently.