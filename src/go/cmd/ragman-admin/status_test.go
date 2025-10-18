package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestRenderStatusTextMatchesGolden(t *testing.T) {
	view := StatusView{
		LatestJobID:        "job-123",
		LatestJobStatus:    "completed",
		CacheDiskPercent:   42.5,
		CacheHitRate:       78,
		ActiveModels:       []string{"gemma3:1b", "codegemma:2b"},
		ManPagesProcessed:  1234,
		WikiArticlesLoaded: 567,
		Progress: ProgressView{
			Stage:           "indexing",
			PercentComplete: 75.0,
			RetryCount:      1,
		},
		Schedule: ScheduleView{
			Cadence:       "24h",
			NextRunAt:     "2025-01-01T12:00:00Z",
			LastSuccessAt: "2025-01-01T09:00:00Z",
		},
		Eviction: EvictionView{
			TotalEntries:        2048,
			TotalBytes:          536870912,
			BudgetBytes:         1073741824,
			LastEvictionAt:      "",
			LastEvictionRemoved: 12,
			LastEvictionBytes:   12345678,
		},
	}

	output, err := RenderStatus(view, FormatText)
	if err != nil {
		t.Fatalf("RenderStatus returned error: %v", err)
	}

	expected := readGolden(t, "status_text.golden")
	if output != expected {
		t.Fatalf("text output mismatch\nexpected:\n%s\n\ngot:\n%s", expected, output)
	}
}

func TestRenderStatusJSONMatchesGolden(t *testing.T) {
	view := StatusView{
		LatestJobID:        "job-123",
		LatestJobStatus:    "failed",
		CacheDiskPercent:   65.1,
		CacheHitRate:       32,
		ActiveModels:       []string{"gemma3:1b"},
		ManPagesProcessed:  222,
		WikiArticlesLoaded: 333,
		IngestionErrors:    []string{"failed to ingest linux-desktop"},
		Progress: ProgressView{
			Stage:           "running",
			PercentComplete: 40.0,
			RetryCount:      3,
		},
		Schedule: ScheduleView{
			Cadence:       "12h30m",
			NextRunAt:     "2025-01-02T02:30:00Z",
			LastSuccessAt: "2025-01-01T19:45:00Z",
		},
		Eviction: EvictionView{
			TotalEntries:        512,
			TotalBytes:          268435456,
			BudgetBytes:         536870912,
			LastEvictionAt:      "2024-12-31T23:59:00Z",
			LastEvictionRemoved: 7,
			LastEvictionBytes:   6543210,
		},
	}

	output, err := RenderStatus(view, FormatJSON)
	if err != nil {
		t.Fatalf("RenderStatus returned error: %v", err)
	}

	expected := readGolden(t, "status_json.golden")
	if output != expected {
		t.Fatalf("json output mismatch\nexpected:\n%s\n\ngot:\n%s", expected, output)
	}
}

func readGolden(t *testing.T, name string) string {
	t.Helper()
	path := filepath.Join("testdata", name)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("failed to read golden file %s: %v", path, err)
	}
	return string(data)
}
