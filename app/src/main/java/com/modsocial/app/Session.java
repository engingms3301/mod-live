package com.modsocial.app;
import android.content.Context;
import android.util.Base64;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import javax.crypto.*;
import javax.crypto.spec.GCMParameterSpec;
import java.security.KeyStore;
import java.nio.charset.StandardCharsets;

final class Session {
 private final Context context;
 Session(Context c){context=c;}
 private javax.crypto.SecretKey key()throws Exception{
  KeyStore ks=KeyStore.getInstance("AndroidKeyStore");ks.load(null);
  if(!ks.containsAlias("mod_session")){
   KeyGenerator g=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
   g.init(new KeyGenParameterSpec.Builder("mod_session",KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());g.generateKey();
  }
  return (javax.crypto.SecretKey)ks.getKey("mod_session",null);
 }
 void save(String token)throws Exception{
  Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.ENCRYPT_MODE,key());
  String data=Base64.encodeToString(c.getIV(),Base64.NO_WRAP)+":"+Base64.encodeToString(c.doFinal(token.getBytes(StandardCharsets.UTF_8)),Base64.NO_WRAP);
  context.getSharedPreferences("mod_auth",0).edit().putString("token",data).apply();
 }
 String load(){try{
  String data=context.getSharedPreferences("mod_auth",0).getString("token","");if(data.isEmpty())return "";
  String[] a=data.split(":");Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,Base64.decode(a[0],Base64.NO_WRAP)));
  return new String(c.doFinal(Base64.decode(a[1],Base64.NO_WRAP)),StandardCharsets.UTF_8);
 }catch(Exception e){clear();return "";}}
 void clear(){context.getSharedPreferences("mod_auth",0).edit().remove("token").apply();}
}
