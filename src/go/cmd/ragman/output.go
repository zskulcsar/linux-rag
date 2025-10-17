package main

import "fmt"

// OutputFormat describes the rendering format used for CLI answers.
type OutputFormat string

const (
	// FormatText renders output in human-readable text form.
	FormatText OutputFormat = "text"
	// FormatJSON renders output as JSON payload.
	FormatJSON OutputFormat = "json"
)

// CitationView represents metadata for a cited document.
type CitationView struct {
	SourceID   string
	Title      string
	Snippet    string
	SourcePath string
}

// AnswerView captures the information surfaced to CLI users.
type AnswerView struct {
	Query          string
	SessionID      string
	Answer         string
	Model          string
	ResponseTimeMS int
	CacheHit       bool
	Citations      []CitationView
}

// RenderAnswer renders a CLI answer according to the requested format.
func RenderAnswer(view AnswerView, format OutputFormat) (string, error) {
	return "", fmt.Errorf("RenderAnswer not implemented for format %s", format)
}
