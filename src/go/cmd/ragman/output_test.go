package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func sampleAnswerView() AnswerView {
	return AnswerView{
		Query:          "How do I enable automount on boot?",
		SessionID:      "session-123",
		Answer:         "Use systemd automount units to mount the share on-demand.",
		Model:          "gemma3:1b",
		ResponseTimeMS: 842,
		CacheHit:       false,
		Citations: []CitationView{
			{
				SourceID:   "doc-1",
				Title:      "systemd.automount - Automount unit configuration",
				Snippet:    "Create an automount unit pointing at your mount unit.",
				SourcePath: "/var/lib/linux-rag/man/systemd.automount",
			},
			{
				SourceID:   "doc-2",
				Title:      "fstab best practices",
				Snippet:    "Use noauto,x-systemd.automount to enable lazy mounting.",
				SourcePath: "/var/lib/linux-rag/wiki/fstab-best-practices",
			},
		},
	}
}

func readGolden(t *testing.T, name string) string {
	t.Helper()
	path := filepath.Join("testdata", name)
	bytes, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("failed to read golden file %s: %v", path, err)
	}
	return string(bytes)
}

func TestRenderAnswerJSONMatchesGolden(t *testing.T) {
	view := sampleAnswerView()

	output, err := RenderAnswer(view, FormatJSON)
	if err != nil {
		t.Fatalf("RenderAnswer returned error: %v", err)
	}

	expected := readGolden(t, "answer_json.golden")
	if strings.TrimSpace(output) != strings.TrimSpace(expected) {
		t.Fatalf("json output mismatch\nexpected:\n%s\n\ngot:\n%s", expected, output)
	}
}

func TestRenderAnswerTextMatchesGolden(t *testing.T) {
	view := sampleAnswerView()

	output, err := RenderAnswer(view, FormatText)
	if err != nil {
		t.Fatalf("RenderAnswer returned error: %v", err)
	}

	expected := readGolden(t, "answer_text.golden")
	if strings.TrimSpace(output) != strings.TrimSpace(expected) {
		t.Fatalf("text output mismatch\nexpected:\n%s\n\ngot:\n%s", expected, output)
	}
}
