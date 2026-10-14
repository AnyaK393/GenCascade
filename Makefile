# Shared entry point. Targets live in each side's own makefile so the two
# never edit the same lines. Run `make help` for the list.
.DEFAULT_GOAL := help

-include control/control.mk
-include platform/platform.mk

.PHONY: help
help:
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
