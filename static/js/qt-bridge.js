(function () {
  if (!window.__QT_WRAPPER__ || typeof QWebChannel === 'undefined') return;
  new QWebChannel(qt.webChannelTransport, function (channel) {
    window.qtBridge = channel.objects.bridge;
  });
})();
