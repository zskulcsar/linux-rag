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
		payload := map[string]any{
			"query":            view.Query,
			"session_id":       view.SessionID,
			"answer":           view.Answer,
			"model":            view.Model,
			"response_time_ms": view.ResponseTimeMS,
			"cache_hit":        view.CacheHit,
			"citations":        make([]map[string]string, 0, len(view.Citations)),
		}
		for _, citation := range view.Citations {
			payload["citations"] = append(payload["citations"].([]map[string]string), map[string]string{
				"id":          citation.SourceID,
				"title":       citation.Title,
				"snippet":     citation.Snippet,
				"source_path": citation.SourcePath,
			})
		}

		bytes, err := json.MarshalIndent(payload, "", "  ")
		if err != nil {
			return "", fmt.Errorf("failed to render json: %w", err)
		}
		return string(bytes), nil

	case FormatText:
		var b strings.Builder
		cacheState := "miss"
		if view.CacheHit {
			cacheState = "hit"
		}

		fmt.Fprintf(&b, "Question: %s\n", view.Query)
		fmt.Fprintf(&b, "Session: %s\n", view.SessionID)
		fmt.Fprintf(&b, "Model: %s\n", view.Model)
		fmt.Fprintf(&b, "Latency: %dms\n", view.ResponseTimeMS)
		fmt.Fprintf(&b, "Cache: %s\n\n", cacheState)

		b.WriteString(view.Answer)

		if len(view.Citations) > 0 {
			b.WriteString("\n\nSources:\n")
			for i, citation := range view.Citations {
				fmt.Fprintf(&b, "[%d] %s\n", i+1, citation.Title)
				fmt.Fprintf(&b, "    %s\n", citation.SourcePath)
				snippet := strings.TrimSpace(citation.Snippet)
				if snippet != "" {
					fmt.Fprintf(&b, "    %s\n", snippet)
				}
				b.WriteString("\n")
			}
			output := b.String()
			return strings.TrimRight(output, "\n"), nil
		}

		return b.String(), nil
	default:
		return "", fmt.Errorf("unsupported format %q", format)
	}
}
