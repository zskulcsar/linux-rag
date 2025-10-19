package main

import (
	"encoding/json"
	"fmt"
	"strings"
)

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
	switch format {
	case FormatJSON:
		bytes, err := renderAnswerJSON(view)
		if err != nil {
			return "", fmt.Errorf("failed to render json: %w", err)
		}
		return bytes, nil

	case FormatText:
		return renderAnswerText(view), nil
	default:
		return "", fmt.Errorf("unsupported format %q", format)
	}
}

// renderAnswerJSON produces deterministic JSON output for answers.
func renderAnswerJSON(view AnswerView) (string, error) {
	type citation struct {
		ID         string `json:"id"`
		Title      string `json:"title"`
		Snippet    string `json:"snippet"`
		SourcePath string `json:"source_path"`
	}
	type payload struct {
		Query         string     `json:"query"`
		SessionID     string     `json:"session_id"`
		Answer        string     `json:"answer"`
		Model         string     `json:"model"`
		ResponseTime  int        `json:"response_time_ms"`
		CacheHit      bool       `json:"cache_hit"`
		CitationViews []citation `json:"citations"`
	}

	body := payload{
		Query:        view.Query,
		SessionID:    view.SessionID,
		Answer:       view.Answer,
		Model:        view.Model,
		ResponseTime: view.ResponseTimeMS,
		CacheHit:     view.CacheHit,
	}
	if len(view.Citations) > 0 {
		body.CitationViews = make([]citation, 0, len(view.Citations))
		for _, c := range view.Citations {
			body.CitationViews = append(body.CitationViews, citation{
				ID:         c.SourceID,
				Title:      c.Title,
				Snippet:    c.Snippet,
				SourcePath: c.SourcePath,
			})
		}
	}

	bytes, err := json.MarshalIndent(body, "", "  ")
	if err != nil {
		return "", err
	}
	return string(bytes), nil
}

// renderAnswerText builds a human-readable answer with citation formatting.
func renderAnswerText(view AnswerView) string {
	var b strings.Builder

	fmt.Fprintf(&b, "Question: %s\n", view.Query)
	fmt.Fprintf(&b, "Session: %s\n", view.SessionID)
	fmt.Fprintf(&b, "Model: %s\n", view.Model)
	fmt.Fprintf(&b, "Latency: %dms\n", view.ResponseTimeMS)
	fmt.Fprintf(&b, "Cache: %s\n\n", cacheState(view.CacheHit))

	b.WriteString(view.Answer)

	if len(view.Citations) > 0 {
		b.WriteString("\n\nSources:\n")
		for i, c := range view.Citations {
			b.WriteString(renderCitationText(i, c))
		}
	}

	return strings.TrimRight(b.String(), "\n")
}

func cacheState(hit bool) string {
	if hit {
		return "hit"
	}
	return "miss"
}

func renderCitationText(index int, citation CitationView) string {
	var b strings.Builder
	fmt.Fprintf(&b, "[%d] %s\n", index+1, citation.Title)
	fmt.Fprintf(&b, "    %s\n", citation.SourcePath)

	snippet := strings.TrimSpace(citation.Snippet)
	if snippet != "" {
		fmt.Fprintf(&b, "    %s\n", snippet)
	}

	b.WriteString("\n")
	return b.String()
}
