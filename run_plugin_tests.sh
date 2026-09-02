#!/bin/bash
# Comprehensive test runner for Plugins 31-42 (Batch 4)

set -e

MARKETPLACE_DIR="/home/shumway/projects/Corvin-Marketplace"
PYTHON="${PYTHON:-python3}"

echo "=========================================="
echo "Corvin-Marketplace Plugin Batch 4 Tests"
echo "Plugins 31-42: Full Test Suite"
echo "=========================================="
echo ""

# Check if pytest is installed
if ! $PYTHON -m pip list | grep -q pytest; then
    echo "[INFO] pytest not installed. Installing..."
    $PYTHON -m pip install pytest pytest-asyncio -q
fi

# Test configuration
export PYTHONPATH="$MARKETPLACE_DIR:$PYTHONPATH"

# Define test directories
TEST_DIRS=(
    "plugins/contributor/data_processing/sql_expert/tests"
    "plugins/contributor/integration/slack_notifier/tests"
    "plugins/contributor/memory/nlp_toolkit/tests"
)

TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Run unit tests for each plugin
echo "[UNIT TESTS] Running plugin unit tests..."
echo ""

for test_dir in "${TEST_DIRS[@]}"; do
    plugin_name=$(echo $test_dir | cut -d/ -f4)

    if [ -d "$MARKETPLACE_DIR/$test_dir" ]; then
        echo "Testing $plugin_name..."

        test_files=$(find "$MARKETPLACE_DIR/$test_dir" -name "test_*.py")

        for test_file in $test_files; do
            echo "  Running: $(basename $test_file)"

            if $PYTHON -m pytest "$test_file" -v --tb=short -q 2>&1 | tee /tmp/test_output.log; then
                PASSED_TESTS=$((PASSED_TESTS + 1))
                echo "    ✓ PASSED"
            else
                FAILED_TESTS=$((FAILED_TESTS + 1))
                echo "    ✗ FAILED (see above)"
            fi

            TOTAL_TESTS=$((TOTAL_TESTS + 1))
        done

        echo ""
    fi
done

echo "[E2E TESTS] Running end-to-end tests..."
echo ""

# Run E2E tests
for test_dir in "${TEST_DIRS[@]}"; do
    plugin_name=$(echo $test_dir | cut -d/ -f4)

    if [ -d "$MARKETPLACE_DIR/$test_dir" ]; then
        e2e_files=$(find "$MARKETPLACE_DIR/$test_dir" -name "e2e_test_*.py")

        for test_file in $e2e_files; do
            echo "Testing E2E: $(basename $test_file)"

            if $PYTHON -m pytest "$test_file" -v --tb=short -q 2>&1 | tee /tmp/e2e_output.log; then
                PASSED_TESTS=$((PASSED_TESTS + 1))
                echo "  ✓ PASSED"
            else
                FAILED_TESTS=$((FAILED_TESTS + 1))
                echo "  ✗ FAILED (see above)"
            fi

            TOTAL_TESTS=$((TOTAL_TESTS + 1))
        done
    fi
done

echo ""
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo "Total Tests:  $TOTAL_TESTS"
echo "Passed:       $PASSED_TESTS"
echo "Failed:       $FAILED_TESTS"
echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    echo "✓ ALL TESTS PASSED!"
    exit 0
else
    echo "✗ SOME TESTS FAILED"
    exit 1
fi
