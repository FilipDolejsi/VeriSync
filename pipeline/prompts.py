"""
Prompt templates for LangGraph nodes.
"""

CLASSIFIER_PROMPT = """You are a code classification expert. Analyze the following code diff and classify it into exactly ONE single-word category.

Valid categories: logic, style, security, performance, tests, docs, refactor

Code Diff:
{diff_text}

Respond with ONLY the single word category, nothing else."""

REVIEWER_PROMPT = """You are an expert code reviewer. Analyze the following code diff and identify issues.

Code Diff:
{diff_text}

Language: {language}
Category: {tag}

For each issue found, provide:
1. A clear description of the issue
2. Severity level (critical, major, or minor)
3. Suggested fix (if applicable)

Format your response as a JSON array with objects like:
{{"issue": "...", "severity": "...", "line_number": null, "suggestion": "..."}}

Focus on:
- Security vulnerabilities
- Performance problems
- Logic errors
- Code quality issues
- Best practice violations

Provide ONLY the JSON array, no other text."""

VERIFIER_PROMPT = """You are a verification expert. Review the following code diff and the findings reported by a reviewer.

Code Diff:
{diff_text}

Reported Findings:
{findings}

Task: Verify if these findings are accurate and should be raised to the PR author.
- Check if findings are based on actual code issues
- Assess if findings are constructive and actionable
- Identify if any findings are false positives

Respond with either:
- "ACCEPT: All findings are valid and should be raised." or
- "REJECT: Some findings are not valid." with explanation

Be concise but thorough."""

SYNTHESISER_PROMPT = """You are a senior engineer synthesizing code review findings.

PR ID: {pr_id}
Total Findings: {total_findings}

Findings Summary:
{findings}

Task: Create a concise executive summary and list 3-5 priority action items.

Format:
SUMMARY: [2-3 sentences summarizing the review]
PRIORITY_ACTIONS: [JSON array of actions with keys: "action", "reason", "priority" (high/medium/low)]

Example:
SUMMARY: The PR introduces security concerns and performance issues...
PRIORITY_ACTIONS: [{{"action": "Fix SQL injection vulnerability", "reason": "User input not sanitized", "priority": "high"}}, ...]

Respond with ONLY the formatted output."""
