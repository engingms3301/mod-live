package com.modsocial.app;
import org.json.JSONObject;
import java.net.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
final class Api {
 static final class Failure extends IOException {final int status;Failure(int status,String message){super(message);this.status=status;}}
 static JSONObject request(String base,String token,String method,String path,JSONObject body)throws Exception{
  URL url=new URL(base+path);if(!url.getProtocol().equals("https"))throw new IOException("Güvenli bir HTTPS sunucu adresi gerekli.");
  HttpURLConnection c=(HttpURLConnection)url.openConnection();c.setConnectTimeout(12000);c.setReadTimeout(15000);c.setInstanceFollowRedirects(false);c.setRequestMethod(method);c.setRequestProperty("Accept","application/json");
  if(!token.isEmpty())c.setRequestProperty("Authorization","Bearer "+token);
  try {
   if(body!=null){c.setDoOutput(true);c.setRequestProperty("Content-Type","application/json; charset=utf-8");try(OutputStream o=c.getOutputStream()){o.write(body.toString().getBytes(StandardCharsets.UTF_8));}}
   int code=c.getResponseCode();InputStream in=code>=400?c.getErrorStream():c.getInputStream();ByteArrayOutputStream out=new ByteArrayOutputStream();
   if(in!=null)try(InputStream stream=in){byte[] b=new byte[4096];int n;while((n=stream.read(b))!=-1){if(out.size()+n>4*1024*1024)throw new IOException("Sunucu yanıtı çok büyük.");out.write(b,0,n);}}
   JSONObject result;try{result=new JSONObject(out.toString("UTF-8"));}catch(Exception e){throw new IOException("Sunucudan geçerli yanıt alınamadı.");}
   if(code<200||code>=300)throw new Failure(code,result.optString("error","İşlem tamamlanamadı."));return result;
  }finally{c.disconnect();}
 }
}
