package controller

import (
	_ "go_learn/model"
	"io"
	"net/http"

	"github.com/gin-gonic/gin"
)

// GetLogsList godoc
//
//	@Summary		Get logs content
//	@Description	get log content
//	@Tags			logs
//	@Accept			json
//	@Produce		json
//	@Param			id	path		int	true	"Account ID"
//	@Success		200	{object}	model.Log
//	@Failure		400	{object}	Response{data=object} "success"
//	@Failure		404	{object}	Response "somthing is wrong"
//	@Router			/logs/content [get]
func (c *Controller) GetLogsList(ctx *gin.Context) {
	data, err := c.service.GetLogsList()

	if err != nil {
		APIResponse(ctx, http.StatusInternalServerError, "error", err.Error())
		return
	}

	APIResponse(ctx, http.StatusOK, "success", data)
}

func (c *Controller) GetLogsContent(ctx *gin.Context) {
	file, err := c.service.OpenLogsStream()
	if err != nil {
		APIResponse(ctx, http.StatusInternalServerError, "error", err.Error())
		return
	}
	defer file.Close()

	ctx.Header("Content-Type", "text/plain; charset=utf-8")
	ctx.Header("Content-Disposition", `inline; filename="edge-core-20260825.log"`)

	if _, err := io.Copy(ctx.Writer, file); err != nil {
		ctx.Error(err)
		return
	}
}
