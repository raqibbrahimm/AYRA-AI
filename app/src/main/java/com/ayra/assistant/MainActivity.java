package com.ayra.assistant;

import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebChromeClient;

public class MainActivity extends Activity {
    private WebView ayra;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        ayra = new WebView(this);
        ayra.getSettings().setJavaScriptEnabled(true);
        ayra.getSettings().setDomStorageEnabled(true);
        ayra.setWebViewClient(new WebViewClient());
        ayra.setWebChromeClient(new WebChromeClient());

        setContentView(ayra);
        ayra.loadUrl("file:///android_asset/index.html");
    }

    @Override
    public void onBackPressed() {
        if (ayra != null && ayra.canGoBack()) {
            ayra.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
