package io.github.mcdrsingleplayer.mixin;

import com.google.gson.Gson;
import io.github.mcdrsingleplayer.ClosingJsonReader;
import java.io.IOException;
import java.io.Reader;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

/** Syncmatica 0.3.20 leaves this FileReader open after loading a world's config. */
@Pseudo
@Mixin(targets = "ch.endte.syncmatica.Context", remap = false)
public abstract class SyncmaticaContextMixin {
    @Redirect(method = "loadConfiguration", at = @At(value = "INVOKE",
            target = "Lcom/google/gson/Gson;fromJson(Ljava/io/Reader;Ljava/lang/Class;)Ljava/lang/Object;"),
            remap = false, require = 0)
    private Object mcdrCloseConfigurationReader(Gson gson, Reader reader, Class<?> type) throws IOException {
        return ClosingJsonReader.read(gson, reader, type);
    }
}
